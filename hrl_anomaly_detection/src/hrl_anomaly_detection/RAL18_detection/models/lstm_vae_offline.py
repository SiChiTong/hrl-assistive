#!/usr/bin/env python
#
# Copyright (c) 2014, Georgia Tech Research Corporation
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#     * Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright
#       notice, this list of conditions and the following disclaimer in the
#       documentation and/or other materials provided with the distribution.
#     * Neither the name of the Georgia Tech Research Corporation nor the
#       names of its contributors may be used to endorse or promote products
#       derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY GEORGIA TECH RESEARCH CORPORATION ''AS IS'' AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL GEORGIA TECH BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA,
# OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE
# OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF
# ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#

#  \author Daehyung Park (Healthcare Robotics Lab, Georgia Tech.)

# system & utils
import os, sys, copy, random
import numpy
import numpy as np
import scipy

# Keras
import h5py 
from keras.models import Sequential, Model
from keras.layers import Merge, Input, TimeDistributed, Layer
from keras.layers import Activation, Dropout, Flatten, Dense, merge, Lambda, RepeatVector, LSTM, GaussianNoise
from keras.layers.advanced_activations import PReLU, LeakyReLU
from keras.utils.np_utils import to_categorical
from keras.optimizers import SGD, Adagrad, Adadelta, RMSprop, Adam
from keras import backend as K
from keras import objectives

from hrl_anomaly_detection.vae import keras_util as ku
from hrl_anomaly_detection.vae import util as vutil

import gc



def lstm_vae(trainData, testData, weights_file=None, batch_size=1024, nb_epoch=500, \
             patience=20, fine_tuning=False, save_weights_file=None, noise_mag=0.0, sam_epoch=512,\
             x_std_div=1, x_std_offset=0.001, z_std=0.5,
             re_load=False, renew=False, plot=True, **kwargs):
    """
    Variational Autoencoder with two LSTMs and one fully-connected layer
    x_train is (sample x length x dim)
    x_test is (sample x length x dim)
    """    
    x_train = trainData[0]
    y_train = trainData[1]
    x_test = testData[0]
    y_test = testData[1]

    timesteps = len(x_train[0])
    input_dim = len(x_train[0][0])

    h1_dim = input_dim
    z_dim  = 2

    inputs = Input(shape=(timesteps, input_dim)) #1.99
    ## encoded = GaussianNoise(noise_mag)(inputs)
    encoded = LSTM(h1_dim, return_sequences=False, activation='tanh')(inputs)
    z_mean  = Dense(z_dim)(encoded) 
    z_log_var = Dense(z_dim)(encoded) 
    
    def sampling(args):
        z_mean, z_log_var = args
        epsilon = K.random_normal(shape=K.shape(z_mean), mean=0., stddev=z_std)
        ## epsilon = K.random_normal(shape=(z_dim,), mean=0., stddev=1.0)
        return z_mean + K.exp(z_log_var/2.0) * epsilon    
        
    # we initiate these layers to reuse later.
    decoded_h1 = Dense(z_dim, name='h_1') 
    decoded_h2 = RepeatVector(timesteps, name='h_2')
    decoded_L21 = LSTM(input_dim*2, return_sequences=True, activation='sigmoid', name='L_21')

    # Custom loss layer
    class CustomVariationalLayer(Layer):
        def __init__(self, **kwargs):
            self.is_placeholder = True
            super(CustomVariationalLayer, self).__init__(**kwargs)

        def vae_loss(self, x, x_d_mean, x_d_std):
            log_p_x_z = -0.5 * ( K.sum(K.square((x-x_d_mean)/x_d_std), axis=-1) \
                                 + float(input_dim) * K.log(2.0*np.pi) + K.sum(K.log(K.square(x_d_std)),
                                                                               axis=-1) )
            xent_loss = K.mean(-log_p_x_z, axis=-1)

            kl_loss = - 0.5 * K.sum(1 + z_log_var - K.square(z_mean) - K.exp(z_log_var), axis=-1)
            return K.mean(xent_loss + kl_loss) 
        
        def call(self, args):
            x = args[0]
            x_d_mean = args[1][:,:,:input_dim]
            x_d_std  = args[1][:,:,input_dim:]/x_std_div + x_std_offset
            
            loss = self.vae_loss(x, x_d_mean, x_d_std)
            self.add_loss(loss, inputs=args)
            # We won't actually use the output.
            return x_d_mean
 

    z = Lambda(sampling)([z_mean, z_log_var])    
    decoded = decoded_h1(z)
    decoded = decoded_h2(decoded)
    decoded = decoded_L21(decoded)
    outputs = CustomVariationalLayer()([inputs, decoded])

    vae_autoencoder = Model(inputs, outputs)
    print(vae_autoencoder.summary())

    # Encoder --------------------------------------------------
    vae_encoder_mean = Model(inputs, z_mean)
    vae_encoder_var  = Model(inputs, z_log_var)

    # Decoder (generator) --------------------------------------
    ## decoder_input = Input(shape=(z_dim,))
    ## _decoded = decoded_h1(decoder_input)
    ## _decoded = decoded_h2(_decoded)
    ## _decoded = decoded_L21(_decoded)
    ## generator = Model(decoder_input, _decoded)
    generator = None

    # VAE --------------------------------------
    vae_mean_std = Model(inputs, decoded)

    if weights_file is not None and os.path.isfile(weights_file) and fine_tuning is False and\
        re_load is False and renew is False:
        vae_autoencoder.load_weights(weights_file)
    else:
        if fine_tuning:
            vae_autoencoder.load_weights(weights_file)
            lr = 0.0001
            optimizer = Adam(lr=lr, clipvalue=10)                
            vae_autoencoder.compile(optimizer=optimizer, loss=None)
        else:
            if re_load and os.path.isfile(weights_file):
                vae_autoencoder.load_weights(weights_file)
            vae_autoencoder.compile(optimizer='adam', loss=None)
            

        ## vae_autoencoder.load_weights(weights_file)
        from keras.callbacks import EarlyStopping, ReduceLROnPlateau, ModelCheckpoint
        callbacks = [EarlyStopping(monitor='val_loss', min_delta=0, patience=patience,
                                   verbose=0, mode='auto'),
                    ModelCheckpoint(weights_file,
                                    save_best_only=True,
                                    save_weights_only=True,
                                    monitor='val_loss'),
                    ReduceLROnPlateau(monitor='val_loss', factor=0.2,
                                      patience=3, min_lr=0.0)]

        train_datagen = ku.sigGenerator(augmentation=True, noise_mag=noise_mag)
        train_generator = train_datagen.flow(x_train, x_train, batch_size=batch_size, seed=3334,
                                             shuffle=True)
        
        hist = vae_autoencoder.fit_generator(train_generator,
                                             steps_per_epoch=sam_epoch,
                                             epochs=nb_epoch,
                                             validation_data=(x_test, x_test),
                                             callbacks=callbacks)
        ## if save_weights_file is not None:
        ##     vae_autoencoder.save_weights(save_weights_file)
        ## else:
        ##     vae_autoencoder.save_weights(weights_file)

        gc.collect()


    # ---------------------------------------------------------------------------------
    # visualize outputs
    if plot:
        print "variance visualization"
        nDim = len(x_test[0,0])
        
        for i in xrange(len(x_test)):

            x = x_test[i:i+1]

            vae_autoencoder.reset_states()
            vae_mean_std.reset_states()
            
            x_pred_mean = []
            x_pred_std  = []
            
            x_pred = vae_mean_std.predict(x)
            x_pred_mean = x_pred[0,:,:nDim]
            x_pred_std  = x_pred[0,:,nDim:]/x_std_div+x_std_offset

            vutil.graph_variations(x_test[i], x_pred_mean, x_pred_std)

        
    return vae_autoencoder, vae_mean_std, vae_mean_std, vae_encoder_mean, vae_encoder_var, generator
    
