# Reads realtime data from a buffer in subscriber node
# predicts the future 10-20 timesteps
# Using Animation plot both the original position and predicted position
# Using Animation plot both the original sound and predicted sound
# Using Soundplay or PyAudio play predicted sound in real time
import rosbag
import rospy
import numpy as np
import matplotlib.pyplot as plt
import librosa
import os, copy, sys
import tensorflow as tf
import numpy.matlib
import scipy as sp
import scipy.interpolate
from sklearn import preprocessing

from keras.models import load_model
from keras.models import Sequential
from keras.layers import Dense, Activation, LSTM, Dropout, RepeatVector, TimeDistributed, Input
from keras.models import Sequential, Model
from keras import optimizers
from keras import backend as K

import config as cf
import pyaudio
from std_msgs.msg import String, Float64, Float64MultiArray, MultiArrayLayout
from hrl_multimodal_prediction.msg import audio, pub_relpos, pub_mfcc, plot_pub
from visualization_msgs.msg import Marker
import hrl_lib.circular_buffer as cb
from scipy import fft, arange, signal, fftpack

# Predictor and visualizer go hand in hand
# Predict 10 time steps and save in a variable
# unlock mutex_viz
# variable read from visualizer, plot and lock mutex_viz -- wait for predicted value
# repeat
class predictor():
	posUpdate = False
	mfccUpdate = False
	relpos = None
	mfcc = None
	timestamp_mfcc = None
	timestamp_relpos = None

	model = None #LSTM Model
	graph = None
	stream = None
	plot_publisher = None

	init_relpos_x = None
	init_flag = True
	out_p, out_m = None, None
	init_out_flag = True
	
	init_orig_mfcc = None
	init_mfcc_flag = True

	end_relpos_x = None
	end_flag = False
	cnt = 0
	
	else_flag = True
	posx_buf  = cb.CircularBuffer(10, (1,))

	def __init__(self):
		print 'initiating...'
		self.p = pyaudio.PyAudio()
		self.stream = self.p.open(format=pyaudio.paFloat32, channels=1, rate=44100, 
								output=True, input_device_index=0)
		
		# audio and image minmax of training data
		mm = np.load(cf.PROCESSED_DATA_PATH + 'combined_train_minmax.npy')		
		self.a_min, self.a_max, self.i_min, self.i_max = mm[0], mm[1], mm[2], mm[3]
		# print self.a_min, self.a_max, self.i_min, self.i_max

		# must publish original and predicted for visualizer
		self.plot_publisher = rospy.Publisher('orig_pred_plotData', plot_pub, queue_size=10)

	def define_network(self, batch_size, time_in, time_out, input_dim, n_neurons):
		model = Sequential()
		model.add(LSTM(input_dim*time_out, batch_input_shape=(batch_size, time_in, input_dim),
						stateful=True, return_sequences=True, activation='tanh'))
		model.add(LSTM(input_dim*time_out, stateful=True, return_sequences=True, activation='tanh'))
		model.add(TimeDistributed(Dense(input_dim*time_out, activation='linear')))

		model.load_weights('./weights/0.00283601_0.00190106real_data.h5')
		model.compile(loss='mse', optimizer='RMSprop')
		print model.summary()
		print "Inputs: {}".format(model.input_shape)
		print "Outputs: {}".format(model.output_shape)
		return model

	def reconstruct_mfcc(self, mfccs, timestep):
		#build reconstruction mappings
		n_mfcc = mfccs.shape[0]
		n_mel = cf.N_MEL
		dctm = librosa.filters.dct(n_mfcc, n_mel)
		n_fft = cf.N_FFT
		mel_basis = librosa.filters.mel(cf.RATE, n_fft, n_mels=n_mel)

		#Empirical scaling of channels to get ~flat amplitude mapping.
		bin_scaling = 1.0/np.maximum(0.0005, np.sum(np.dot(mel_basis.T, mel_basis), axis=0))
		#Reconstruct the approximate STFT squared-magnitude from the MFCCs.
		recon_stft = bin_scaling[:, np.newaxis] * np.dot(mel_basis.T, self.invlogamplitude(np.dot(dctm.T, mfccs)))
		#Impose reconstructed magnitude on white noise STFT.
		excitation = np.random.randn(cf.HOP_LENGTH*timestep-1) # this will be constant--based on one msgsize
		E = librosa.stft(excitation, n_fft=n_fft)
		recon = librosa.istft(E/np.abs(E)*np.sqrt(recon_stft))
		#print recon
		#print recon.shape
		# wav.write('reconsturct.wav', cf.RATE, recon)
		return recon

	def invlogamplitude(self, S):
	#"""librosa.logamplitude is actually 10_log10, so invert that."""
		return 10.0**(S/10.0)

	def normalize_recon(self, y, min_y, max_y):
		y = (y - min_y) / (max_y - min_y)
		return y

	def play_sound_realtime(self, mfcc):
		if (self.init_relpos_x - self.relpos[0]) > 0.015 and self.else_flag:
			# print mfcc.shape #(1,10,3)
			mfcc = mfcc.reshape(cf.MFCC_DIM, cf.TIMESTEP_OUT)
			# print mfcc.shape
			recon = self.reconstruct_mfcc(mfcc, cf.TIMESTEP_OUT)
			# print recon.shape #(4096,)
			recon = self.normalize(recon, self.a_min, self.a_max)
			# for i in range(recon.shape[0]):
			# 	if recon[i] < 0:
			# 		recon[i] = -np.abs(recon[i])**(np.exp(1.3))
			# 	else:
			# 		recon[i] = recon[i]**(np.exp(1.3))
			
			# n = 1  # the larger n is, the smoother curve will be
			# b = [1.0 / n] * n
			# a = 1
			# recon = signal.lfilter(b,a,recon)

			data = recon.astype(np.float32).tostring()
			self.stream.write(data, exception_on_underflow=False)
		else:
			# print mfcc.shape #(1,5,3)
			mfcc = mfcc.reshape(cf.MFCC_DIM, cf.P_MFCC_TIMESTEP)
			# print mfcc.shape
			recon = self.reconstruct_mfcc(mfcc, cf.P_MFCC_TIMESTEP)
			# print recon.shape #(4096,)
			recon = self.normalize(recon, self.a_min, self.a_max)
			# for i in range(recon.shape[0]):
			# 	if recon[i] < 0:
			# 		recon[i] = -np.abs(recon[i])**(np.exp(1.3))
			# 	else:
			# 		recon[i] = recon[i]**(np.exp(1.3))

			n = 1  # the larger n is, the smoother curve will be
			b = [1.0 / n] * n
			a = 1
			recon = signal.lfilter(b,a,recon)

			data = recon.astype(np.float32).tostring()
			self.stream.write(data, exception_on_underflow=False)
			data = recon.astype(np.float32).tostring()
			self.stream.write(data, exception_on_underflow=False)
		
	def normalize(self, y, min_y, max_y):
		# normalize to range (-1,1)
		#NewValue = (((OldValue - OldMin) * (NewMax - NewMin)) / (OldMax - OldMin)) + NewMin
		y = (((y - min_y) * (1 + 1)) / (max_y - min_y)) -1

		# this normalizes to (0,1)
		# y = (y - min_y) / (max_y - min_y)
		return y

	def scale_back(self, seq, min_y, max_y):
		#scale back from -1 1 range
		seq = (((seq + 1)*(max_y - min_y)) / (1 + 1)) + min_y

		# scale back 
		# seq = seq * (max_y - min_y) + min_y
		return seq

	def callback(self, data):
		if data._type == 'hrl_multimodal_prediction/pub_mfcc':
			self.mfcc = data.mfcc
			self.timestamp_mfcc = data.header.stamp
			self.mfccUpdate = True

		elif data._type == 'hrl_multimodal_prediction/pub_relpos':
			self.relpos = data.relpos
			self.timestamp_relpos = data.header.stamp
			self.posUpdate = True
			if self.init_flag:
				self.init_relpos_x = self.relpos[0]
				self.init_flag = False

			#Circular Buffer, take last 5 samples, if avg is <=-0.0103, then stop
			# self.posx_buf.append(self.relpos[0])
			# print np.mean(self.posx_buf.get_last(5))
			# if np.mean(self.posx_buf.get_last(5)) <= -0.009:
			# 	self.else_flag = False

		if self.mfccUpdate and self.posUpdate:
			if ((self.init_relpos_x - self.relpos[0]) > 0.015) and self.else_flag:
				print 'start predict'
				self.posUpdate = False
				self.mfccUpdate = False

				# Timestamp for combined msg to be published
				loc_timestamp_mfcc = self.timestamp_mfcc 
				loc_timestamp_relpos = self.timestamp_relpos

				# print np.array(self.mfcc).shape
				# Convert shape to fit LSTM
				orig_mfcc = np.array(self.mfcc).reshape(1, cf.P_MFCC_TIMESTEP, cf.N_MFCC) # shape=(t, n_mfcc)
				orig_relpos = np.array(self.relpos).reshape(1, 1, cf.IMAGE_DIM) 			

				# print self.mfcc.shape, self.relpos.shape
				tmp = orig_relpos
				for i in range(cf.P_MFCC_TIMESTEP-1): #make position data match mfcc timestep aka interpolating
					orig_relpos = np.concatenate((orig_relpos,tmp), axis=1)
				# print self.mfcc.shape, self.relpos.shape

				# Rescale perFeature, save Scaler
				norm_mfcc = self.normalize(orig_mfcc, self.a_min, self.a_max)
				norm_relpos = self.normalize(orig_relpos, self.i_min, self.i_max)

				# Combine two modes 
				comb_data = np.concatenate((norm_mfcc, norm_relpos), axis=2)
				# print comb_data.shape
				comb_data = np.array(comb_data)

				# Predict -- graph default must to fix multithread bug in keras-tensorflow
				with self.graph.as_default():
					for i in range(0, cf.P_MFCC_TIMESTEP):
						pred = self.model.predict_on_batch(comb_data[:,i:i+1,:])
				#Now pred has the last value
				pred = pred.reshape(1, cf.TIMESTEP_OUT, cf.INPUT_DIM)
				# print pred.shape

				# # Scaleback --only the last one to play nd plot in realtime
				#**********************************************************************
				# SCALE - MUST BE SAVED FROM THE TRAINING DATA, SCALED BACK -- SCALE of TOTAL DATA
				#**********************************************************************
				sb_mfcc = self.scale_back(pred[:,:,0:3], self.a_min, self.a_max)
				sb_relpos = self.scale_back(pred[:,:,3:6], self.i_min, self.i_max) 
				# print sb_mfcc.shape, sb_relpos.shape

				# Play -- Not detecting sound device, Use a Latop for this
				self.play_sound_realtime(sb_mfcc)

				# Publish for plot
				# Getting the last time step of orig and pred and flattening for msg
				sb_mfcc = np.array(sb_mfcc).reshape(cf.TIMESTEP_OUT*cf.MFCC_DIM)
				sb_relpos = np.array(sb_relpos).reshape(cf.TIMESTEP_OUT*cf.IMAGE_DIM)
				orig_mfcc = np.array(orig_mfcc[:,cf.P_MFCC_TIMESTEP-1,:]).reshape(cf.MFCC_DIM)
				orig_relpos = np.array(orig_relpos[:,cf.P_MFCC_TIMESTEP-1,:]).reshape(cf.IMAGE_DIM)
				# print orig_mfcc.shape, orig_relpos.shape, sb_mfcc.shape, sb_relpos.shape
				
				# print orig_mfcc
				# print orig_relpos
				# print sb_mfcc
				# print sb_relpos
				#received messages need to be reshaped in visualizer
				msg = plot_pub()
				msg.header.stamp.secs = (loc_timestamp_relpos.secs + loc_timestamp_mfcc.secs)/2
				msg.header.stamp.nsecs = (loc_timestamp_relpos.nsecs + loc_timestamp_mfcc.nsecs)/2
				msg.orig_mfcc = orig_mfcc
				msg.orig_relpos = orig_relpos
				msg.pred_mfcc = sb_mfcc
				msg.pred_relpos = sb_relpos
				self.plot_publisher.publish(msg)

			else:
				print 'else'
				self.posUpdate = False
				self.mfccUpdate = False

				# Timestamp for combined msg to be published
				loc_timestamp_mfcc = self.timestamp_mfcc 
				loc_timestamp_relpos = self.timestamp_relpos

				# print np.array(self.mfcc).shape
				# Convert shape to fit LSTM
				# print self.mfcc.shape
				orig_mfcc = np.array(self.mfcc).reshape(1, cf.P_MFCC_TIMESTEP, cf.N_MFCC) # shape=(t, n_mfcc)
				orig_relpos = np.array(self.relpos).reshape(1, 1, cf.IMAGE_DIM) 			

				# print self.mfcc.shape, self.relpos.shape
				tmp = orig_relpos
				for i in range(cf.P_MFCC_TIMESTEP-1): #make position data match mfcc timestep aka interpolating
					orig_relpos = np.concatenate((orig_relpos,tmp), axis=1)
				# print self.mfcc.shape, self.relpos.shape

				# Play -- Not detecting sound device, Use a Latop for this
				# self.play_sound_realtime(orig_mfcc)
				if self.init_mfcc_flag:
					self.init_orig_mfcc = orig_mfcc
					self.init_mfcc_flag = False
				self.play_sound_realtime(self.init_orig_mfcc)

				# Publish for plot
				# Getting the last time step of orig and pred and flattening for msg
				orig_mfcc = np.array(orig_mfcc[:,cf.P_MFCC_TIMESTEP-1,:]).reshape(cf.MFCC_DIM)
				orig_relpos = np.array(orig_relpos[:,cf.P_MFCC_TIMESTEP-1,:]).reshape(cf.IMAGE_DIM)
				# print orig_mfcc.shape, orig_relpos.shape, sb_mfcc.shape, sb_relpos.shape
				
				#received messages need to be reshaped in visualizer
				msg = plot_pub()
				msg.header.stamp.secs = (loc_timestamp_relpos.secs + loc_timestamp_mfcc.secs)/2
				msg.header.stamp.nsecs = (loc_timestamp_relpos.nsecs + loc_timestamp_mfcc.nsecs)/2
				msg.orig_mfcc = orig_mfcc
				msg.orig_relpos = orig_relpos

				if self.init_out_flag:
					self.init_out_flag = False
					m1 = np.full(10, orig_mfcc[0])
					m2 = np.full(10, orig_mfcc[1])
					m3 = np.full(10, orig_mfcc[2])
					out_m = np.vstack((m1,m2,m3))
					self.out_m = np.swapaxes(out_m, 0,1).flatten()
					x = np.full((1,10), orig_relpos[0])
					y = np.full((1,10), orig_relpos[1])
					z = np.full((1,10), orig_relpos[2])
					out_p = np.vstack((x,y,z))
					self.out_p = np.swapaxes(out_p, 0,1).flatten()
				# if not self.else_flag:
				# 	x = np.full((1,10), orig_relpos[0])
				# 	y = np.full((1,10), orig_relpos[1])
				# 	z = np.full((1,10), orig_relpos[2])
				# 	out_p = np.vstack((x,y,z))
				# 	self.out_p = np.swapaxes(out_p, 0,1).flatten()

				msg.pred_mfcc = self.out_m
				msg.pred_relpos = self.out_p
				self.plot_publisher.publish(msg)

	def run(self):
		rospy.init_node('predictor', anonymous=True)
		# while not rospy.is_shutdown():
		rospy.Subscriber('preprocessed_audio', pub_mfcc, self.callback)
		rospy.Subscriber('preprocessed_relpos', pub_relpos, self.callback)
		rospy.spin()
		
def main():
	p = predictor()
	p.graph = tf.get_default_graph()
	p.model = p.define_network(cf.PRED_BATCH_SIZE, cf.TIMESTEP_IN, cf.TIMESTEP_OUT, cf.INPUT_DIM, cf.N_NEURONS)
	p.run()


if __name__ == '__main__':
	main()    
