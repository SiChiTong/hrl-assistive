#!/usr/bin/python
#
# Copyright (c) 2017, Georgia Tech Research Corporation
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
#  \author Michael Park (Healthcare Robotics Lab, Georgia Tech.)

import rosbag
import rospy
import os, copy, sys
import librosa
## from hrl_msgs.msg import FloatArray
## from std_msgs.msg import Float64
from hrl_multimodal_prediction.msg import audio

# util
import numpy as np
import math
import pyaudio
import struct
import array
# try:
#     from features import mfcc
# except:
#     from python_speech_features import mfcc
# from scipy import signal, fftpack, conj, stats

import scipy.io.wavfile as wav
import glob

import scipy as sp
import scipy.interpolate
import re
import optparse

from matplotlib import pyplot 

import config as cf
import random

#Psuedo
# First read in all rosbag files from the folder (check)
# find the peak and +- 2s --> audio for one bag (check)
# Downsample, increase window size for one bag
# Plot and check for one bag (check)
# Convert to MFCC and reconstruct for one bag if not good, adjust 3
# Do 2,3,4 for all bags

class dataset_creator:

	def convert_bag2dataset(self):         
		audio_data = []
		image_data = []
		combined_data = []

		if cf.BAG2DATA_TESTDATA:
			path = cf.ROSBAG_TEST_PATH
		else:
			path = cf.ROSBAG_PATH

		for filename in sorted(glob.glob(os.path.join(path, '*.bag'))):
			num = re.findall(r'\d+', filename)
			# bagfile  = ROSBAG_PATH + 'data1.bag'
			# wavfile  = ROSBAG_PATH + 'data1.wav'
			# wavfileMFCC = ROSBAG_PATH + 'data1MFCC.wav'
			# txtfile = ROSBAG_PATH + 'data1.txt'
			bagfile  = filename
			txtfile = cf.ROSBAG_UNPACK_PATH + 'data' + str(num) + 'txt'
			wavfile  = cf.ROSBAG_UNPACK_PATH + 'data' + str(num) + '.wav'
			wavfileMFCC = cf.ROSBAG_UNPACK_PATH + 'data' + str(num) + 'MFCC.wav'

			static_ar = []
			dynamic_ar = []
			audio_store = []
			audio_samples = []
			time_store = []
			audio_t = []
			ars_t = []
			ard_t = []

			for topic, msg, t in rosbag.Bag(bagfile).read_messages():
				#print msg
				if msg._type == 'hrl_anomaly_detection/audio':
					# print np.array(msg.audio_data, dtype=np.int16).shape
					audio_store.append(np.array(msg.audio_data, dtype=np.int16))
					audio_t.append(t)
				elif msg._type == 'visualization_msgs/Marker':
					if msg.id == 0: #id 0 = static
						# print np.array([msg.pose.position.x, msg.pose.position.y, msg.pose.position.z]).shape
						static_ar.append([msg.pose.position.x, msg.pose.position.y, msg.pose.position.z])
						ars_t.append(t)
					elif msg.id == 9: #id 9 = dynamic
						dynamic_ar.append([msg.pose.position.x, msg.pose.position.y, msg.pose.position.z])
						ard_t.append(t)
				time_store.append(t)
			
			static_ar = np.array(static_ar, dtype=np.float64)
			dynamic_ar = np.array(dynamic_ar, dtype=np.float64)
			# print np.array(audio_store).shape
			# print static_ar.shape
			# print dynamic_ar.shape

			##################################
			# Find max of the raw data to find peak and +-88200 samples
			# how to line up image data? interpolate and downsample?
			##################################
			audio_store = np.hstack(audio_store)
			audio_store = np.array(audio_store, dtype=np.float64)
			npmax = np.max(audio_store)
			npmin =  np.min(audio_store)
			print 'before crop'
			# print audio_store.shape
			# print dynamic_ar.shape

			############################################
			### Interpolate xyz and get relative pos ###
			############################################
			#audio 
			new_length = audio_store.shape[0] #upsampling a lot for images but doesn't matter
			#static
			static_ar_intp = self.interpolate(static_ar, new_length)
			#dynamic
			dynamic_ar_intp = self.interpolate(dynamic_ar, new_length) 

			#relative
			relative_position = []
			for i in range(new_length):
				relative_position.append(static_ar_intp[i] - dynamic_ar_intp[i])
			relative_position = np.array(relative_position)
			
			#uncropped
			# a_max = np.max(audio_store)
			# a_min =  np.min(audio_store)
			# audio_store = (audio_store - a_min) / (a_max - a_min)
			# librosa.output.write_wav(ROSBAG_PATH + 'uncroppeddata1.wav', audio_store, self.RATE)
			# np.savetxt(ROSBAG_PATH + 'uncroppeddata1.txt', relative_position)

			########################
			#### Cropping
			########################
			peak_idx = audio_store.tolist().index(npmax)          
			var = cf.RATE/8
			peak_range = int(cf.RATE*0.75)
			print peak_range
			r = random.randrange(0,var) #11025 = 0.25s, so 0.25s variation
			b = random.randrange(0,2)
			while (peak_idx+peak_range+r>audio_store.shape[0]) or (peak_idx-peak_range-r<0): #RATE=1s
				var = var - 500
				r = random.randrange(0,var) #11025 = 0.25s, so 0.25s variation
				b = random.randrange(0,2)
			audio_store = self.crop2s(audio_store, peak_idx,r,b, peak_range)
			relative_position = self.crop2s(relative_position, peak_idx,r,b, peak_range)
			print audio_store.shape, relative_position.shape


			############### MFCC ##########################
			y = audio_store
			sr = cf.RATE
			# Original #
			mfccs = librosa.feature.mfcc(y=y, sr=cf.RATE, hop_length=cf.HOP_LENGTH, n_fft=cf.N_FFT, n_mfcc=cf.N_MFCC)# default hop_length=512, hop_length=int(0.01*sr))
			mfcc_len = mfccs.shape[1]
			############################
			
			###################################
			# mapping xyz to mfcc
			new_length = mfcc_len
			relative_position_intp = self.interpolate(relative_position, new_length) 
			##################################
			
			if cf.BAG2DATA_UNPACK:
				unpack_fp = cf.ROSBAG_UNPACK_PATH + 'data' + str(num) 
				audio_store_unpack = self.normalize(audio_store)
				librosa.output.write_wav(wavfile, audio_store_unpack, cf.RATE)
				np.save(unpack_fp +'_audio_'+'.npy', audio_store)
				np.save(unpack_fp +'_mfccs_'+'.npy', mfccs)
				np.save(unpack_fp +'_relpos_intp_'+'.npy', relative_position_intp)

			if cf.BAG2DATA_UNPACK:
				self.reconstruct_mfcc(mfccs, y, wavfileMFCC)        

			# Fact:: mfcc_len = (sr*sec)/hop_length = (sr*sec)/(n_fft/4)
			print mfccs.shape
			print relative_position_intp.shape
			print '------ ------'

			mfccs = np.rollaxis(mfccs, 1, 0)
			audio_data.append(mfccs)
			image_data.append(relative_position_intp)

			# print filename
			# pyplot.plot(mfccs[:,0])
			# pyplot.plot(mfccs[:,1])
			# pyplot.plot(mfccs[:,2])
			# pyplot.show()
			# pyplot.plot(relative_position_intp[:,0])
			# pyplot.plot(relative_position_intp[:,1])
			# pyplot.plot(relative_position_intp[:,2])
			# pyplot.show()

		#Below here should be outside the loop
		audio_data = np.array(audio_data)
		image_data = np.array(image_data)
		print audio_data.shape
		print image_data.shape
		if not cf.BAG2DATA_TESTDATA:
			a_min, a_max = np.min(audio_data), np.max(audio_data)
			i_min, i_max = np.min(image_data), np.max(image_data)
			print a_min, a_max, i_min, i_max
			minmax = [a_min, a_max, i_min, i_max]
			print 'saving train minmax as npy'
			np.save(cf.PROCESSED_DATA_PATH + 'combined_train_minmax', minmax)
		# else:
		# 	a_min, a_max = np.min(audio_data), np.max(audio_data)
		# 	i_min, i_max = np.min(image_data), np.max(image_data)
		# 	print a_min, a_max, i_min, i_max
		# 	minmax = [a_min, a_max, i_min, i_max]
		# 	print 'saving test minmax as npy'
		# 	np.save(cf.PROCESSED_DATA_PATH + 'combined_test_minmax', minmax)

		#concatenate for number of experiment samples
		# audio_dataX2 = audio_dataX[0]
		# audio_dataY2 = audio_dataY[0]
		# image_dataX2 = image_dataX[0]
		# image_dataY2 = image_dataY[0]
		# for i in range(1, audio_dataX.shape[0]):
		#     audio_dataX2 = np.concatenate((audio_dataX2, audio_dataX[i]), axis=0)
		#     audio_dataY2 = np.concatenate((audio_dataY2, audio_dataY[i]), axis=0)
		#     image_dataX2 = np.concatenate((image_dataX2, image_dataX[i]), axis=0)
		#     image_dataY2 = np.concatenate((image_dataY2, image_dataY[i]), axis=0)
		# audio_dataX = audio_dataX2
		# audio_dataY = audio_dataY2
		# image_dataX = image_dataX2
		# image_dataY = image_dataY2
		# print audio_dataX.shape
		# print audio_dataY.shape
		# print image_dataX.shape
		# print image_dataY.shape

		#normalize by feature
		# a_max = np.max(audio_dataX)
		# a_min =  np.min(audio_dataX)
		# i_max = np.max(image_dataX)
		# i_min =  np.min(image_dataX)
		# audio_dataX = self.normalize(audio_dataX) 
		# audio_dataY = self.normalize(audio_dataY)
		# image_dataX = self.normalize(image_dataX) 
		# image_dataY = self.normalize(image_dataY)
		# audio_dataX = np.array(audio_dataX, dtype=float)
		# audio_dataY = np.array(audio_dataY, dtype=float) 
		# image_dataX = np.array(image_dataX, dtype=float)
		# image_dataY = np.array(image_dataY, dtype=float)

		#combine
		combined_data = np.concatenate((audio_data, image_data), axis=2)
		# combined_dataY = np.concatenate((audio_dataY, image_dataY), axis=1)
		print 'audio image combined'
		print combined_data.shape
		# print combined_dataY.shape

		# a_minmax = []
		# a_minmax.append(a_min)
		# a_minmax.append(a_max)
		# a_minmax = np.array(a_minmax)
		# i_minmax = []
		# i_minmax.append(i_min)
		# i_minmax.append(i_max)
		# i_minmax = np.array(i_minmax)
		#save as np
		if cf.BAG2DATA_TESTDATA:
			np.save(cf.PROCESSED_DATA_PATH + 'combined_test', combined_data)
		else: 
			print 'saving combined train data as npy'
			np.save(cf.PROCESSED_DATA_PATH + 'combined_train', combined_data)

	# def construct_dataset(self, data):
	#     # Create a windowed set dX_audio, dY_audio, concatenate, normalize(91,mfcc)
	#     dX, dY = [], []
	#     for i in range(data.shape[0] - self.WINDOW_SIZE_IN):
	#         dX.append(data[i:i+self.WINDOW_SIZE_IN])
	#         dY.append(data[i+self.WINDOW_SIZE_IN:i+self.WINDOW_SIZE_IN+self.WINDOW_SIZE_OUT][0])
	#     return dX, dY        

	def normalize(self, data):
		a_max = np.max(data)
		a_min =  np.min(data)
		data = (data - a_min) / (a_max - a_min)
		return data

	def crop2s(self, data, peak_idx, r, b, audio_len_sample): #1s=44100, 2s=88200
		data = data[peak_idx-audio_len_sample+r : peak_idx+audio_len_sample+r]

		# if b:
		# 	data = data[peak_idx-audio_len_sample-r : peak_idx+audio_len_sample-r]
		# else:
		# 	data = data[peak_idx-audio_len_sample+r : peak_idx+audio_len_sample+r]
		return data

	def interpolate(self, data, new_length):
		time_len = data.shape[0] 
		feature_len = data.shape[1] 
		l = np.arange(time_len)
		data = np.rollaxis(data, 1, 0)
		f1=sp.interpolate.interp1d(l, data[0]) #x
		f2=sp.interpolate.interp1d(l, data[1]) #y
		f3=sp.interpolate.interp1d(l, data[2]) #z

		data_intp = np.zeros((feature_len, new_length))
		data_intp[0] = f1(np.linspace(0,time_len-1, new_length))
		data_intp[1] = f2(np.linspace(0,time_len-1, new_length))
		data_intp[2] = f3(np.linspace(0,time_len-1, new_length))
		data_intp = np.rollaxis(data_intp, 1, 0)    
		return data_intp

	def reconstruct_mfcc(self, mfccs, y, wavfileMFCC):
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
		excitation = np.random.randn(y.shape[0])
		E = librosa.stft(excitation, n_fft=n_fft)
		recon = librosa.istft(E/np.abs(E)*np.sqrt(recon_stft))
		#print recon
		#print recon.shape
		wav.write(wavfileMFCC, cf.RATE, recon)

	def invlogamplitude(self, S):
	#"""librosa.logamplitude is actually 10_log10, so invert that."""
		return 10.0**(S/10.0)


def main():
	rospy.init_node('convert_bag2dataset')
	dc = dataset_creator()
	dc.convert_bag2dataset()

if __name__ == '__main__':
	main()


