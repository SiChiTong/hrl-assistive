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
import scipy, numpy as np
import hrl_lib.util as ut

# Private utils
from hrl_anomaly_detection import data_manager as dm
from hrl_anomaly_detection import util as util
import hrl_anomaly_detection.isolator.isolation_util as iutil
from hrl_execution_monitor.keras import keras_model as km
from hrl_execution_monitor.keras import keras_util as kutil
from hrl_execution_monitor import viz as eviz
from hrl_anomaly_detection.isolator import keras_models as km_old
from joblib import Parallel, delayed

random.seed(3334)
np.random.seed(3334)

from sklearn import preprocessing
import h5py
import cv2

from keras.preprocessing.image import ImageDataGenerator
from keras.models import Sequential, Model
## from keras.layers import Convolution2D, MaxPooling2D, ZeroPadding2D, Merge, Input
## from keras.layers import Activation, Dropout, Flatten, Dense, merge
## from keras.layers.normalization import BatchNormalization
from keras.utils.np_utils import to_categorical
from keras.optimizers import SGD, Adagrad, Adadelta, RMSprop
from keras.utils.visualize_util import plot
from keras.callbacks import EarlyStopping, ReduceLROnPlateau


vgg_model_weights_path = os.path.expanduser('~')+'/git/keras_test/vgg16_weights.h5'
## nb_train_samples = 1000 #len(x_train)
## nb_validation_samples = 200 #len(x_test)
## nb_train_samples = 500 #2000
## nb_validation_samples = 200 #800
## nb_epoch = 200


def load_data(idx, save_data_path, viz=False):
    ''' Load selected fold's data '''

    assert os.path.isfile(os.path.join(save_data_path,'x_train_img_'+str(idx)+'.npy')) == True, \
      "No preprocessed data"
        
    x_train_sig = np.load(open(os.path.join(save_data_path,'x_train_sig_'+str(idx)+'.npy')))
    x_train_img = np.load(open(os.path.join(save_data_path,'x_train_img_'+str(idx)+'.npy')))
    y_train = np.load(open(os.path.join(save_data_path,'y_train_'+str(idx)+'.npy')))

    x_test_sig = np.load(open(os.path.join(save_data_path,'x_test_sig_'+str(idx)+'.npy')))
    x_test_img = np.load(open(os.path.join(save_data_path,'x_test_img_'+str(idx)+'.npy')))
    y_test = np.load(open(os.path.join(save_data_path,'y_test_'+str(idx)+'.npy')))

    return (x_train_sig, x_train_img, y_train), (x_test_sig, x_test_img, y_test)


def preprocess_data(save_data_path, scaler=4, n_labels=12, viz=False, hog_feature=False,
                    org_ratio=False):
    ''' Preprocessing data '''
    ## from sklearn import preprocessing
    ## scaler = preprocessing.StandardScaler()

    d = ut.load_pickle(os.path.join(save_data_path, 'isol_data.pkl'))
    nFold = len(d.keys())

    for idx in xrange(nFold):

        (x_trains, y_train, x_tests, y_test) = d[idx]         
        x_train_sig = x_trains[0] #signals
        x_test_sig  = x_tests[0]
        x_train_img = x_trains[1] #img
        x_test_img  = x_tests[1]
        print "Training data: ", np.shape(x_train_img), np.shape(x_train_sig), np.shape(y_train)
        print "Testing data: ", np.shape(x_test_img), np.shape(x_test_sig), np.shape(y_test)

        #--------------------------------------------------------------------
        # check images
        rm_idx = []
        x_train = []
        for j, f in enumerate(x_train_img):
            if f is None:
                print "None image ", j+1, '/', len(x_train_img)
                rm_idx.append(j)
                continue

            if hog_feature is False:
                if org_ratio:
                    img = cv2.imread(f)
                    height, width = np.array(img).shape[:2]
                    img = cv2.resize(img,(width/scaler, height/scaler), interpolation = cv2.INTER_CUBIC)
                    img = img.astype(np.float32)
                else:
                    # BGR, vgg
                    img_size = (256,256)
                    img = cv2.resize(cv2.imread(f), img_size).astype(np.float32)
                    crop_size = (224,224)
                    img = img[(img_size[0]-crop_size[0])//2:(img_size[0]+crop_size[0])//2
                              ,(img_size[1]-crop_size[1])//2:(img_size[1]+crop_size[1])//2,:]

                # for vgg but lets use
                img[:,:,0] -= 103.939
                img[:,:,1] -= 116.779
                img[:,:,2] -= 123.68

                if viz:
                    print np.shape(img), type(img), type(img[0][0][0])
                    # visual check
                    cv2.imshow('image',img)
                    cv2.waitKey(0)
                    cv2.destroyAllWindows()
                    sys.exit()

                img = img.transpose((2,0,1))
            else:
                ## img = cv2.imread(f,0)
                ## height, width = np.array(img).shape[:2]
                ## scaler = 1
                ## img = cv2.resize(img,(width/scaler, height/scaler), interpolation = cv2.INTER_CUBIC)
                ## img = hog(img, bin_n=16)

                img = cv2.imread(f)
                gray= cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)
                sift = cv2.xfeatures2d.SIFT_create()
                kp = sift.detect(gray,None)
                img=cv2.drawKeypoints(gray,kp,img)
                print np.shape(img)
                sys.exit()
                
            x_train.append(img)
        x_train_img = x_train

        # check signals and labels
        x_train_sig = [x_train_sig[i] for i in xrange(len(x_train_sig)) if i not in rm_idx ]
        y_train = [y_train[i] for i in xrange(len(y_train)) if i not in rm_idx ]
        y_train = np.array(y_train)-2 # make label start from zero
        if hog_feature is False:
            y_train = to_categorical(y_train, nb_classes=n_labels)

        np.save(open(os.path.join(save_data_path,'x_train_img_'+str(idx)+'.npy'), 'w'), x_train_img)
        np.save(open(os.path.join(save_data_path,'x_train_sig_'+str(idx)+'.npy'), 'w'), x_train_sig)
        np.save(open(os.path.join(save_data_path,'y_train_'+str(idx)+'.npy'), 'w'), y_train)

        #--------------------------------------------------------------------
        # check images
        rm_idx = []
        x_test = []
        for j, f in enumerate(x_test_img):
            if f is None:
                print "None image ", j+1, '/', len(x_test_img)
                rm_idx.append(j)
                continue

            if hog_feature is False:
                if org_ratio:
                    img = cv2.imread(f)
                    height, width = np.array(img).shape[:2]
                    img = cv2.resize(img,(width/scaler, height/scaler), interpolation = cv2.INTER_CUBIC)
                    img = img.astype(np.float32)
                else:                    
                    img = cv2.resize(cv2.imread(f), (224, 224)).astype(np.float32)
                img[:,:,0] -= 103.939
                img[:,:,1] -= 116.779
                img[:,:,2] -= 123.68
                img = img.transpose((2,0,1))
            else:
                ## img = cv2.imread(f,0)
                ## height, width = np.array(img).shape[:2]
                ## scaler = 1
                ## img = cv2.resize(img,(width/scaler, height/scaler), interpolation = cv2.INTER_CUBIC)
                ## img = hog(img, bin_n=16)

                img = cv2.imread(f)
                gray= cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)
                sift = cv2.xfeatures2d.SIFT_create()
                kp = sift.detect(gray,None)
                img=cv2.drawKeypoints(gray,kp,img)

            x_test.append(img)
        x_test_img = x_test

        # check singlas
        x_test_sig = [x_test_sig[i] for i in xrange(len(x_test_sig)) if i not in rm_idx  ]
        y_test = [y_test[i] for i in xrange(len(y_test)) if i not in rm_idx  ]
        y_test = np.array(y_test)-2 # make label start from zero
        if hog_feature is False:
            y_test = to_categorical(y_test, nb_classes=n_labels)

        np.save(open(os.path.join(save_data_path,'x_test_img_'+str(idx)+'.npy'), 'w'), x_test_img)
        np.save(open(os.path.join(save_data_path,'x_test_sig_'+str(idx)+'.npy'), 'w'), x_test_sig)
        np.save(open(os.path.join(save_data_path,'y_test_'+str(idx)+'.npy'), 'w'), y_test)




def hog(img, bin_n=16):
    gx = cv2.Sobel(img, cv2.CV_32F, 1, 0)
    gy = cv2.Sobel(img, cv2.CV_32F, 0, 1)
    mag, ang = cv2.cartToPolar(gx, gy)
    bins = np.int32(bin_n*ang/(2*np.pi))    # quantizing binvalues in (0...16)
    bin_cells = bins[:10,:10], bins[10:,:10], bins[:10,10:], bins[10:,10:]
    mag_cells = mag[:10,:10], mag[10:,:10], mag[:10,10:], mag[10:,10:]
    hists = [np.bincount(b.ravel(), m.ravel(), bin_n) for b, m in zip(bin_cells, mag_cells)]
    hist = np.hstack(hists)     # hist is a 64 bit vector
    return hist



def evaluate_svm(save_data_path, viz=False):

    d = ut.load_pickle(os.path.join(save_data_path, 'isol_data.pkl'))
    nFold = len(d.keys())
    del d

    scores = []
    y_test_list = []
    y_pred_list = []
    for idx in xrange(nFold):
        train_data, test_data = load_data(idx, save_data_path, viz=False)      
        x_train_sig = train_data[0]
        x_train_img = train_data[1].astype(np.float32)
        y_train = train_data[2]
        x_test_sig  = test_data[0]
        x_test_img  = test_data[1].astype(np.float32)
        y_test  = test_data[2]        
        print "Data: ", np.shape(x_train_img), np.shape(x_train_sig), np.shape(y_train)

        if len(np.shape(y_train))>1: y_train = np.argmax(y_train, axis=1)
        if len(np.shape(y_test))>1: y_test = np.argmax(y_test, axis=1)

        ## x_train = np.hstack([x_train_sig, x_train_img])
        ## x_test = np.hstack([x_test_sig, x_test_img])
        x_train = x_train_sig
        x_test  = x_test_sig
        ## x_train = x_train_img
        ## x_test  = x_test_img


        print np.shape(x_train)

        x_train_dyn1 = x_train[:,:24]
        x_train_dyn2 = x_train[:,24:-7]#[:,:6]
        x_train_stc = x_train[:,-7:][:,[0,1,2,4,5,6]]
        ## x_train_dyn1 -= np.mean(x_train_dyn1, axis=1)[:,np.newaxis]
        ## x_train_dyn2 -= np.mean(x_train_dyn2, axis=1)[:,np.newaxis]
        x_train = np.hstack([x_train_dyn1, x_train_dyn2, x_train_stc])

        x_test_dyn1 = x_test[:,:24]
        x_test_dyn2 = x_test[:,24:-7]#[:,:6]
        x_test_stc = x_test[:,-7:][:,[0,1,2,4,5,6]]
        ## x_test_dyn1 -= np.mean(x_test_dyn1, axis=1)[:,np.newaxis]
        ## x_test_dyn2 -= np.mean(x_test_dyn2, axis=1)[:,np.newaxis]
        x_test = np.hstack([x_test_dyn1, x_test_dyn2, x_test_stc])
        
        scaler = preprocessing.StandardScaler()
        x_train = scaler.fit_transform(x_train)
        x_test  = scaler.transform(x_test)

        # train svm
        ## from sklearn.svm import SVC
        ## clf = SVC(C=1.0, kernel='rbf', gamma=1e-5) #, decision_function_shape='ovo')
        from sklearn.ensemble import RandomForestClassifier
        clf = RandomForestClassifier(n_estimators=400, n_jobs=-1)
        ## from sklearn.neighbors import KNeighborsClassifier
        ## clf = KNeighborsClassifier(n_neighbors=10, n_jobs=-1)
        clf.fit(x_train, y_train)

        # classify and get scores
        score = clf.score(x_test, y_test)
        scores.append(score)
        print "score: ", score

        if viz:
            y_pred = clf.predict(x_test)
            y_pred_list += y_pred.tolist()
            y_test_list += y_test.tolist()
            
        
    print scores
    print np.mean(scores), np.std(scores)
    if viz: plot_confusion_matrix(y_test_list, y_pred_list)


def unimodal_fc(save_data_path, n_labels, nb_epoch=400, fine_tune=False, activ_type='relu',
                test_only=False, save_pdf=False):

    d = ut.load_pickle(os.path.join(save_data_path, 'isol_data.pkl'))
    nFold = len(d.keys())
    del d

    callbacks = [EarlyStopping(monitor='val_loss', min_delta=0, patience=10, verbose=0, mode='auto')]
    ## callbacks = [EarlyStopping(monitor='val_loss', min_delta=0, patience=3, verbose=0, mode='auto')]
    ## callbacks = [ReduceLROnPlateau(monitor='val_loss', factor=0.2,
    ##                                patience=5, min_lr=0.0001)]

    scores= []
    y_test_list = []
    y_pred_list = []
    for idx in xrange(nFold):

        # Loading data
        train_data, test_data = load_data(idx, save_data_path, viz=False)      
        x_train_sig = train_data[0]
        y_train     = train_data[2]
        x_test_sig = test_data[0]
        y_test     = test_data[2]

        ## x_train_sig_dyn1 = x_train_sig[:,:15]
        ## x_train_sig_dyn2 = x_train_sig[:,15:-7]#[:,[0, 3, 6]]
        ## x_train_sig_stc = x_train_sig[:,-7:]#[:,[0,1,2,4,5,6,7]]

        ## ## x_train_sig_dyn1 /= np.amax(x_train_sig_dyn1, axis=1)[:,np.newaxis]
        ## ## x_train_sig_dyn2 /= np.amax(x_train_sig_dyn2, axis=1)[:,np.newaxis]
        ## x_train_sig = np.hstack([x_train_sig_dyn1, x_train_sig_dyn2, x_train_sig_stc])
        
        ## x_test_sig_dyn1 = x_test_sig[:,:15]
        ## x_test_sig_dyn2 = x_test_sig[:,15:-7]#[:,[0, 3, 6,]]
        ## x_test_sig_stc = x_test_sig[:,-7:]#[:,[0,1,2,4,5,6,7]]
        ## ## x_test_sig_dyn1 /= np.amax(x_test_sig_dyn1, axis=1)[:,np.newaxis]
        ## ## x_test_sig_dyn2 /= np.amax(x_test_sig_dyn2, axis=1)[:,np.newaxis]
        ## x_test_sig = np.hstack([x_test_sig_dyn1, x_test_sig_dyn2, x_test_sig_stc])

        ## print np.shape(x_train_sig), np.shape(x_test_sig)
        ## ## sys.exit()

        ## scaler = preprocessing.MinMaxScaler()
        ## x_train_sig = scaler.fit_transform(x_train_sig)
        ## x_test_sig  = scaler.transform(x_test_sig)        
        scaler      = preprocessing.StandardScaler()
        x_train_sig = scaler.fit_transform(x_train_sig)
        x_test_sig  = scaler.transform(x_test_sig)


        full_weights_path = os.path.join(save_data_path,'sig_weights_'+str(idx)+'.h5')

        ## # Load pre-trained vgg16 model
        if fine_tune is False:
            model = km.sig_net(np.shape(x_train_sig)[1:], n_labels, activ_type=activ_type)
            ## optimizer = SGD(lr=0.001, decay=1e-5, momentum=0.9, nesterov=True)
            optimizer = RMSprop(lr=0.001, rho=0.9, epsilon=1e-08, decay=0.0)
            model.compile(optimizer=optimizer, loss='categorical_crossentropy', metrics=['accuracy'])
            ## model.compile(optimizer='rmsprop', loss='categorical_crossentropy', metrics=['accuracy'])
        else:
            model = km.sig_net(np.shape(x_train_sig)[1:], n_labels, fine_tune=True,\
                               weights_path = full_weights_path, activ_type=activ_type)
        
            ## optimizer = SGD(lr=0.01, decay=1e-5, momentum=0.9, nesterov=True)
            ## optimizer = SGD(lr=0.0001, decay=1e-6, momentum=0.9, nesterov=True)
            optimizer = SGD(lr=0.0001, decay=1e-7, momentum=0.9, nesterov=True)
            ## optimizer = RMSprop(lr=0.00001, rho=0.9, epsilon=1e-08, decay=0.0)
            model.compile(optimizer=optimizer, loss='categorical_crossentropy', metrics=['accuracy'])

        if test_only is False:
            train_datagen = kutil.sigGenerator(augmentation=True, noise_mag=0.05 )
            test_datagen = kutil.sigGenerator(augmentation=False)
            train_generator = train_datagen.flow(x_train_sig, y_train, batch_size=128)
            test_generator = test_datagen.flow(x_test_sig, y_test, batch_size=128)

            hist = model.fit_generator(train_generator,
                                       samples_per_epoch=len(y_train),
                                       nb_epoch=nb_epoch,
                                       validation_data=test_generator,
                                       nb_val_samples=len(y_test),
                                       callbacks=callbacks)

            scores.append( hist.history['val_acc'][-1] )
            model.save_weights(full_weights_path)
            del model
        else:
            model.load_weights(full_weights_path)
            y_pred = model.predict(x_test_sig)
            y_pred_list += np.argmax(y_pred, axis=1).tolist()
            y_test_list += np.argmax(y_test, axis=1).tolist()
            
            from sklearn.metrics import accuracy_score
            print "score : ", accuracy_score(y_test_list, y_pred_list)

            

    print 
    print np.mean(scores), np.std(scores)
    if test_only: plot_confusion_matrix(y_test_list, y_pred_list, save_pdf=save_pdf)
    return

    
def unimodal_cnn(save_data_path, n_labels, nb_epoch=100, fine_tune=False, vgg=False):

    d = ut.load_pickle(os.path.join(save_data_path, 'isol_data.pkl'))
    nFold = len(d.keys())
    del d

    if vgg: prefix = 'vgg_'
    else: prefix = ''

    scores= []
    for idx in xrange(nFold):

        # Loading data
        train_data, test_data = load_data(idx, save_data_path, viz=False)      
        x_train_sig = train_data[0]
        x_train_img = train_data[1]
        y_train     = train_data[2]
        x_test_sig = test_data[0]
        x_test_img = test_data[1]
        y_test     = test_data[2]
        
        full_weights_path = os.path.join(save_data_path,prefix+'cnn_weights_'+str(idx)+'.h5')

        # Load pre-trained vgg16 model
        ## model = km.vgg16_net(np.shape(x_train_img)[1:], n_labels, vgg_model_weights_path, \
        ##                      full_weights_path, fine_tune=False)
        ## model = km.vgg16_net(np.shape(x_train_img)[1:], n_labels, vgg_model_weights_path, \
        ##                      fine_tune=False)

        if fine_tune is False:
            if vgg: model = km.vgg16_net(np.shape(x_train_img)[1:], n_labels, vgg_model_weights_path)
            else: model = km.cnn_net(np.shape(x_train_img)[1:], n_labels)            
            model.compile(optimizer='rmsprop', loss='categorical_crossentropy', metrics=['accuracy'])
        else:
            if vgg: model = km.vgg16_net(np.shape(x_train_img)[1:], n_labels, vgg_model_weights_path,\
                                        full_weights_path)
            else: model = km.cnn_net(np.shape(x_train_img)[1:], n_labels, full_weights_path)
            optimizer = SGD(lr=0.0001, decay=1e-8, momentum=0.9, nesterov=True)
            ## optimizer = RMSprop(lr=0.00001, rho=0.9, epsilon=1e-08, decay=0.0)
            model.compile(optimizer=optimizer, loss='categorical_crossentropy', metrics=['accuracy'])


        train_datagen = ImageDataGenerator(
            rotation_range=20,
            rescale=1./255,
            width_shift_range=0.2,
            height_shift_range=0.2,
            ## zoom_range=0.1,
            horizontal_flip=False,
            fill_mode='nearest',
            dim_ordering="th")
        test_datagen = ImageDataGenerator(rescale=1./255,\
                                          dim_ordering="th")

        train_generator = train_datagen.flow(x_train_img, y_train, batch_size=16)
        test_generator = test_datagen.flow(x_test_img, y_test, batch_size=16)

        hist = model.fit_generator(train_generator,
                                   samples_per_epoch=len(y_train),
                                   nb_epoch=nb_epoch,
                                   validation_data=test_generator,
                                   nb_val_samples=len(y_test))

        model.save_weights(full_weights_path)

        scores.append( hist.history['val_acc'][-1] )

    print 
    print np.mean(scores), np.std(scores)
    return
    
def multimodal_cnn_fc(save_data_path, n_labels, nb_epoch=100, fine_tune=False,
                      test_only=False, save_pdf=False, vgg=False):

    d = ut.load_pickle(os.path.join(save_data_path, 'isol_data.pkl'))
    nFold = len(d.keys())
    del d

    if vgg: prefix = 'vgg_'
    else: prefix = ''

    scores= []
    y_test_list = []
    y_pred_list = []
    for idx in xrange(nFold):

        # Loading data
        train_data, test_data = load_data(idx, save_data_path, viz=False)      
        x_train_sig = train_data[0]
        x_train_img = train_data[1]
        y_train     = train_data[2]
        x_test_sig = test_data[0]
        x_test_img = test_data[1]
        y_test     = test_data[2]

        scaler      = preprocessing.StandardScaler()
        x_train_sig = scaler.fit_transform(x_train_sig)
        x_test_sig  = scaler.transform(x_test_sig)

        ## full_weights_path = os.path.join(save_data_path,'vgg16_weights_'+str(idx)+'.h5')
        ## full_weights_path = os.path.join(save_data_path,'cov_weights_'+str(idx)+'.h5')
        ## full_weights_path = os.path.join(save_data_path,'cnn_fc_weights_'+str(idx)+'.h5')

        # Load pre-trained model
        ## model = km.vgg16_net(np.shape(x_train_img)[1:], n_labels, vgg_model_weights_path, \
        ##                      full_weights_path, fine_tune=False)
        ## model = km.vgg16_net(np.shape(x_train_img)[1:], n_labels, vgg_model_weights_path, \
        ##                      fine_tune=False)
        ## model.save_weights(full_weights_path)--------------------------------------------------
        ## sys.exit()

        if fine_tune is False:
            # training
            if vgg:
                model = km.vgg16_net(np.shape(x_train_img)[1:], n_labels, vgg_model_weights_path,\
                                     with_top=True, fine_tune=False,
                                     input_shape2=np.shape(x_train_sig)[1:] )
            else:
                model = km.cnn_net(np.shape(x_train_img)[1:], n_labels, \
                                   with_top=True, fine_tune=False,
                                   input_shape2=np.shape(x_train_sig)[1:] )
            model.load_weights( os.path.join(save_data_path,'sig_weights_'+str(idx)+'.h5'), by_name=True )
            model.load_weights( os.path.join(save_data_path,prefix+'cnn_weights_'+str(idx)+'.h5'), \
                                by_name=True )
            model.compile(optimizer='rmsprop', loss='categorical_crossentropy', metrics=['accuracy'])
        else:
            # fine tuning
            if vgg:
                model = km.vgg16_net(np.shape(x_train_img)[1:], n_labels, vgg_model_weights_path,\
                                     with_top=True, fine_tune=True,
                                     input_shape2=np.shape(x_train_sig)[1:] )
            else:
                model = km.cnn_net(np.shape(x_train_img)[1:], n_labels, \
                                   with_top=True, fine_tune=True,
                                   input_shape2=np.shape(x_train_sig)[1:] )
            model.load_weights( os.path.join(save_data_path,prefix+'cnn_fc_weights_'+str(idx)+'.h5') )
            optimizer = SGD(lr=0.00001, decay=1e-8, momentum=0.9, nesterov=True)
            ## optimizer = RMSprop(lr=0.00001, rho=0.9, epsilon=1e-08, decay=0.0)
            model.compile(optimizer=optimizer, loss='categorical_crossentropy', metrics=['accuracy'])

                

        if test_only is False:
            train_datagen = kutil.myGenerator(augmentation=True, rescale=1./255.)
            test_datagen = kutil.myGenerator(augmentation=False, rescale=1./255.)
            train_generator = train_datagen.flow(x_train_img, x_train_sig, y_train, batch_size=16)
            test_generator = test_datagen.flow(x_test_img, x_test_sig, y_test, batch_size=16)
            callbacks = [EarlyStopping(monitor='val_loss', min_delta=0, patience=0, verbose=0, mode='auto')]
        
            hist = model.fit_generator(train_generator,
                                       samples_per_epoch=len(y_train),
                                       nb_epoch=50,
                                       validation_data=test_generator,
                                       nb_val_samples=len(y_test),
                                       callbacks=callbacks)

            full_weights_path = os.path.join(save_data_path,prefix+'cnn_fc_weights_'+str(idx)+'.h5')
            model.save_weights(full_weights_path)

            scores.append( hist.history['val_acc'][-1] )
        else:
            model.load_weights( os.path.join(save_data_path,prefix+'cnn_fc_weights_'+str(idx)+'.h5') )
            y_pred = model.predict([x_test_img/255., x_test_sig])
            y_pred_list += np.argmax(y_pred, axis=1).tolist()
            y_test_list += np.argmax(y_test, axis=1).tolist()
            
            from sklearn.metrics import accuracy_score
            print "score : ", accuracy_score(y_test_list, y_pred_list)
            ## break


    print np.mean(scores), np.std(scores)
    if test_only: plot_confusion_matrix(y_test_list, y_pred_list, save_pdf)
    
    

def plot_confusion_matrix(y_test_list, y_pred_list, save_pdf=False):
    classes = ['Object collision', 'Noisy environment', 'Spoon miss by a user', 'Spoon collision by a user', 'Robot-body collision by a user', 'Aggressive eating', 'Anomalous sound from a user', 'Unreachable mouth pose', 'Face occlusion by a user', 'Spoon miss by system fault', 'Spoon collision by system fault', 'Freeze by system fault']


    from sklearn.metrics import confusion_matrix
    cm = confusion_matrix(y_test_list, y_pred_list)

    print np.sum(cm,axis=1)

    eviz.plot_confusion_matrix(cm, classes=classes, normalize=True,
                               title='Anomaly Isolation', save_pdf=save_pdf)
    





if __name__ == '__main__':

    import optparse
    p = optparse.OptionParser()
    util.initialiseOptParser(p)

    p.add_option('--preprocess', '--p', action='store_true', dest='preprocessing',
                 default=False, help='Preprocess')
    p.add_option('--bottom_train', '--bt', action='store_true', dest='bottom_train',
                 default=False, help='Train the bottom layer')
    p.add_option('--top_train', '--tt', action='store_true', dest='top_train',
                 default=False, help='Train the top layer')
    p.add_option('--fine_tune', '--f', action='store_true', dest='fine_tune',
                 default=False, help='Fine tuning')
    p.add_option('--viz', action='store_true', dest='viz',
                 default=False, help='Visualize')
    p.add_option('--viz_model', '--vm', action='store_true', dest='viz_model',
                 default=False, help='Visualize the current model')

    p.add_option('--eval_isol', '--ei', action='store_true', dest='evaluation_isolation',
                 default=False, help='Evaluate anomaly isolation with double detectors.')
    p.add_option('--ai_renew', '--ai', action='store_true', dest='ai_renew',
                 default=False, help='Renew ai')
    p.add_option('--combined_train', '--ct', action='store_true', dest='combined_train',
                 default=False, help='Train all layer')
    
    opt, args = p.parse_args()

    #---------------------------------------------------------------------------           
    # Run evaluation
    #---------------------------------------------------------------------------           
    rf_center     = 'kinEEPos'        
    scale         = 1.0
    local_range   = 10.0
    nPoints = 40 #None

    from hrl_anomaly_detection.isolator.IROS2017_params import *
    raw_data_path, save_data_path, param_dict = getParams(opt.task, opt.bDataRenew, \
                                                          opt.bHMMRenew, opt.bCLFRenew, opt.dim,\
                                                          rf_center, local_range, nPoints=nPoints)
    if opt.bNoUpdate: param_dict['ROC']['update_list'] = []
    # Mikako - bad camera
    # s1 - kaci - before camera calibration
    subjects = ['s2', 's3','s4','s5', 's6','s7','s8', 's9']

    save_data_path = os.path.expanduser('~')+\
      '/hrl_file_server/dpark_data/anomaly/AURO2016/'+opt.task+'_data_isolation3/'+\
      str(param_dict['data_param']['downSampleSize'])+'_'+str(opt.dim)

    n_labels = 12 #len(np.unique(y_train))
    
    # ---------------------------------------------------------------------
    # 1st pre_train top layer
    if opt.preprocessing:
        preprocess_data(save_data_path, viz=opt.viz)

    elif opt.bottom_train:
        bottom_feature_extraction(save_data_path, n_labels, augmentation=True)
                                 
    elif opt.top_train:
        top_model_train(n_labels)
        ## top_model_train2(save_data_path, n_labels, augmentation=False, nb_epoch=10)

    elif opt.fine_tune:
        fine_tune(save_data_path, n_labels)


        
    elif opt.viz:
        x_train, y_train, x_test, y_test = load_data(save_data_path, True)
    elif opt.viz_model:
        model = km.vgg16_net((3,120,160), 12, with_top=True, input_shape2=(14,), viz=True)
        plot(model, to_file='model.png')
        
    else:
        # 148 amin - nofz        
        save_data_path = os.path.expanduser('~')+\
          '/hrl_file_server/dpark_data/anomaly/AURO2016/'+opt.task+'_data_isolation3/'+\
          str(param_dict['data_param']['downSampleSize'])+'_'+str(opt.dim)
        
        # 148 amin
        ## save_data_path = os.path.expanduser('~')+\
        ##   '/hrl_file_server/dpark_data/anomaly/AURO2016/'+opt.task+'_data_isolation4/'+\
        ##   str(param_dict['data_param']['downSampleSize'])+'_'+str(opt.dim)
        
        ## preprocess_data(save_data_path, viz=opt.viz, hog_feature=False, org_ratio=True)

        ## unimodal_fc(save_data_path, n_labels, nb_epoch=200, activ_type='PReLU')        
        ## unimodal_fc(save_data_path, n_labels, nb_epoch=200, fine_tune=True, activ_type='PReLU')        

        # relu
        ## unimodal_fc(save_data_path, n_labels, nb_epoch=200)        
        ## unimodal_fc(save_data_path, n_labels, fine_tune=True, nb_epoch=400)        
        ## unimodal_cnn(save_data_path, n_labels)        
        ## unimodal_cnn(save_data_path, n_labels, fine_tune=True)        
        ## multimodal_cnn_fc(save_data_path, n_labels)
        ## multimodal_cnn_fc(save_data_path, n_labels, fine_tune=True)

        
        ## unimodal_fc(save_data_path, n_labels, nb_epoch=200, test_only=True)        
        ## multimodal_cnn_fc(save_data_path, n_labels, fine_tune=True, test_only=True,
        ##                   save_pdf=opt.bSavePdf)
        evaluate_svm(save_data_path, viz=True)

        ## unimodal_cnn(save_data_path, n_labels, vgg=True)        
        ## unimodal_cnn(save_data_path, n_labels, fine_tune=True, vgg=True)        
        ## multimodal_cnn_fc(save_data_path, n_labels, vgg=True)
        ## multimodal_cnn_fc(save_data_path, n_labels, fine_tune=True, vgg=True)

        


