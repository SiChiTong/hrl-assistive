#!/usr/bin/env python

# System
import numpy as np
import time, sys, threading
import cPickle as pkl
from collections import deque
import pyaudio
import struct
import scipy.signal as signal
import scipy.fftpack
import operator

# ROS
import roslib
roslib.load_manifest('hrl_anomaly_detection')
roslib.load_manifest('geometry_msgs')
roslib.load_manifest('hrl_lib')
import rospy, optparse, math, time
import tf
from geometry_msgs.msg import Wrench
from geometry_msgs.msg import TransformStamped, WrenchStamped
from std_msgs.msg import Bool, Float32

# HRL
from hrl_srvs.srv import None_Bool, None_BoolResponse
from hrl_msgs.msg import FloatArray
import hrl_lib.util as ut

# External Utils
import matplotlib.pyplot as pp
import matplotlib as mpl
from pylab import *


# Private
#import hrl_anomaly_detection.door_opening.mechanism_analyse_daehyung as mad
#import hrl_anomaly_detection.advait.arm_trajectories as at

def log_parse():
    parser = optparse.OptionParser('Input the Pose node name and the ft sensor node name')

    parser.add_option("-t", "--tracker", action="store", type="string",\
    dest="tracker_name", default="adl2")
    parser.add_option("-f", "--force" , action="store", type="string",\
    dest="ft_sensor_name",default="/netft_data")

    (options, args) = parser.parse_args()

    return options.tracker_name, options.ft_sensor_name 


class tool_audio():
    MAX_INT = 32768.0
    CHUNK   = 1024 #frame per buffer
    RATE    = 44100 #sampling rate
    UNIT_SAMPLE_TIME = 1.0 / float(RATE)
    CHANNEL=1 #number of channels
    FORMAT=pyaudio.paInt16
    
    def __init__(self):
        self.DTYPE = np.int16
        
        self.p=pyaudio.PyAudio()
        self.stream=self.p.open(format=self.FORMAT, channels=self.CHANNEL, rate=self.RATE, \
                                input=True, frames_per_buffer=self.CHUNK)
        rospy.logout('Done subscribing audio')

    def audio_cb(self):

        data=self.stream.read(self.CHUNK)
        decoded=np.fromstring(data, self.DTYPE)
        
        frames.append(decoded)
        l=len(frames)
        if l*self.chunk>=3000:
            index=range(0, l-2)
            frames_arr=np.array(frames.popleft())
            for i in index:
                e=frames.popleft()
                frames_arr=np.concatenate((frames_arr, e), axis=0)
            frames_arr.reshape(-1)
            z=((amp_frames_arr-self.mu)/self.sigma)

            a=abs(z)>=self.stddevs*self.sigma

            #Publish ROS messages
            self.audio_analyzer(z)#,data1)

    def reset(self):

        RECORD_SECONDS = 9.0

        # Get noise frequency        
        frames=None
        f  = np.fft.fftfreq(self.CHUNK, self.UNIT_SAMPLE_TIME) 
        n=len(f)
        
        ## for i in range(0, int(self.RATE/self.CHUNK * RECORD_SECONDS)):
        data=self.stream.read(self.CHUNK)
        audio_data=np.fromstring(data, self.DTYPE)

        if frames is None: frames = audio_data
        else: frames = np.hstack([frames, audio_data])
        amp_thres = self.get_rms(data)            

        F = np.fft.fft(audio_data / float(self.MAX_INT))  #normalization & FFT          

        import heapq
        values = heapq.nlargest(3, F[:n/2]) #amplitude

        max_freq_l = []
        for value in values:
            max_freq_l.append([f[j] for j, k in enumerate(F[:n/2]) if k == value])
        max_freq_l = np.array(max_freq_l)


        print "Amplitude threshold: ", amp_thres
        ## pp.figure()
        ## pp.plot(f[:n/4],np.abs(F[:n/4]),'b')
        ## pp.stem(max_freq_l, values, 'r-*', bottom=0)
        ## pp.show()
        raw_input("Enter anything to start: ")
        
        
        def filter_rule(x, freq, max_freq):
            band = 80.0
            if np.abs(freq) > max_freq+band or np.abs(freq) < max_freq-band:
                return x
            else:
                return 0

        # Filter the bandwidth of the noise
        new_frames=None
        new_filt_frames=None
        f  = np.fft.fftfreq(self.CHUNK, self.UNIT_SAMPLE_TIME) 
        n=len(f)
        zero_audio_data = np.zeros(self.CHUNK)
        
        for i in range(0, int(self.RATE/self.CHUNK * RECORD_SECONDS)):
            data=self.stream.read(self.CHUNK)
            audio_data=np.fromstring(data, self.DTYPE)

            if new_frames is None: new_frames = audio_data
            else: new_frames = np.hstack([new_frames, audio_data])


            # Exclude low rms data
            amp = self.get_rms(data)            
            if amp < amp_thres*1.2:
                new_audio_data = zero_audio_data
            else:
                new_F = F = np.fft.fft(audio_data / float(self.MAX_INT))  #normalization & FFT          
                
                # Remove noise
                for max_freq in max_freq_l:
                    new_F = np.array([filter_rule(x,f[j], max_freq) for j, x in enumerate(new_F)])
                new_audio_data = np.fft.ifft(new_F)*float(self.MAX_INT)
            
            if new_filt_frames is None: new_filt_frames = new_audio_data
            else: new_filt_frames = np.hstack([new_filt_frames, new_audio_data])
                

        print new_filt_frames.shape
        ## for i in range(0, int(self.RATE/self.CHUNK * RECORD_SECONDS)):
        ##                
        ##     new_frames.append(string_audio_data)            

        string_audio_data = np.array(new_filt_frames, dtype=self.DTYPE).tostring() 
        import wave
        WAVE_OUTPUT_FILENAME = "/home/dpark/git/pyaudio/test/output.wav"
        wf = wave.open(WAVE_OUTPUT_FILENAME, 'wb')
        wf.setnchannels(self.CHANNEL)
        wf.setsampwidth(self.p.get_sample_size(self.FORMAT))
        wf.setframerate(self.RATE)
        wf.writeframes(b''.join(string_audio_data))
        wf.close()
            

        pp.figure()
        
        pp.subplot(211)
        pp.plot(new_frames,'b-')
        pp.plot(new_filt_frames,'r-')
        
        pp.subplot(212)
        pp.plot(f[:n/10],np.abs(F[:n/10]),'b')
        if new_F is not None:
            pp.plot(f[:n/10],np.abs(new_F[:n/10]),'r')
        pp.stem(max_freq_l, values, 'k-*', bottom=0)
        
        pp.show()

        
                
    def close(self):
        self.stream.stop_stream()
        self.stream.close()

    def get_rms(self, block):
        # Copy from http://stackoverflow.com/questions/4160175/detect-tap-with-pyaudio-from-live-mic
        
        # RMS amplitude is defined as the square root of the 
        # mean over time of the square of the amplitude.
        # so we need to convert this string of bytes into 
        # a string of 16-bit samples...

        # we will get one short out for each 
        # two chars in the string.
        count = len(block)/2
        format = "%dh"%(count)
        shorts = struct.unpack( format, block )

        # iterate over the block.
        sum_squares = 0.0
        for sample in shorts:
        # sample is a signed short in +/- 32768. 
        # normalize it to 1.0
            n = sample / self.MAX_INT
            sum_squares += n*n

        return math.sqrt( sum_squares / count )        

class tool_ft():
    def __init__(self,ft_sensor_topic_name):
        self.init_time = 0.
        self.counter = 0
        self.counter_prev = 0
        self.force = np.matrix([0.,0.,0.]).T
        self.force_raw = np.matrix([0.,0.,0.]).T
        self.torque = np.matrix([0.,0.,0.]).T
        self.torque_raw = np.matrix([0.,0.,0.]).T
        self.torque_bias = np.matrix([0.,0.,0.]).T

        self.time_data = []
        self.force_data = []
        self.force_raw_data = []
        self.torque_data = []
        self.torque_raw_data = []

        #capture the force on the tool tip	
        ## self.force_sub = rospy.Subscriber(ft_sensor_topic_name,\
        ## 	WrenchStamped, self.force_cb)
        #raw ft values from the NetFT
        self.force_raw_sub = rospy.Subscriber(ft_sensor_topic_name,\
        WrenchStamped, self.force_raw_cb)
        ## self.force_zero = rospy.Publisher('/tool_netft_zeroer/rezero_wrench', Bool)
        rospy.logout('Done subscribing to '+ft_sensor_topic_name+' topic')


    def force_cb(self, msg):
        self.force = np.matrix([msg.wrench.force.x, 
        msg.wrench.force.y,
        msg.wrench.force.z]).T
        self.torque = np.matrix([msg.wrench.torque.x, 
        msg.wrench.torque.y,
        msg.wrench.torque.z]).T


    def force_raw_cb(self, msg):
        self.time = msg.header.stamp.to_time()
        self.force_raw = np.matrix([msg.wrench.force.x, 
        msg.wrench.force.y,
        msg.wrench.force.z]).T
        self.torque_raw = np.matrix([msg.wrench.torque.x, 
        msg.wrench.torque.y,
        msg.wrench.torque.z]).T
        self.counter += 1


    def reset(self):
        self.force_zero.publish(Bool(True))
	

    def log(self, log_file):
        if self.counter > self.counter_prev:
            self.counter_prev = self.counter
            time_int = self.time-self.init_time
            print >> log_file, time_int, self.counter,\
            self.force_raw[0,0],self.force_raw[1,0],self.force_raw[2,0],\
            self.torque_raw[0,0],self.torque_raw[1,0],self.torque_raw[2,0]
            ## self.force[0,0],self.force[1,0],self.force[2,0],\
            ## self.torque[0,0],self.torque[1,0],self.torque[2,0],\

            ## self.force_data.append(self.force)
            self.force_raw_data.append(self.force_raw)
            ## self.torque_data.append(self.torque)
            self.torque_raw_data.append(self.torque_raw)
            self.time_data.append(self.time)


    def static_bias(self):
        print '!!!!!!!!!!!!!!!!!!!!'
        print 'BIASING FT'
        print '!!!!!!!!!!!!!!!!!!!!'
        f_list = []
        t_list = []
        for i in range(20):
            f_list.append(self.force)
            t_list.append(self.torque)
            rospy.sleep(2/100.)
        if f_list[0] != None and t_list[0] !=None:
            self.force_bias = np.mean(np.column_stack(f_list),1)
            self.torque_bias = np.mean(np.column_stack(t_list),1)
            print self.gravity
            print '!!!!!!!!!!!!!!!!!!!!'
            print 'DONE Biasing ft'
            print '!!!!!!!!!!!!!!!!!!!!'
        else:
            print 'Biasing Failed!'


class ADL_log():
    def __init__(self):
        rospy.init_node('ADLs_log', anonymous = True)

        self.init_time = 0.
        self.tool_tracker_name, self.ft_sensor_topic_name = log_parse()        
        rospy.logout('ADLs_log node subscribing..')
        
        #subscribe to the rigid body nodes		
        ## self.tflistener = tf.TransformListener()
        ## self.tool_tracker = tracker_pose(tool_tracker_name)
        ## self.head_tracker = tracker_pose('head')


    def task_cmd_input(self):
        confirm = False
        while not confirm:
            valid = True
            self.sub_name=raw_input("Enter subject's name: ")
            num=raw_input("Enter the number for the choice of task:"+\
            "\n1) cup \n2) door \n3) wipe"+\
            "\n4) spoon\n5) tooth brush\n6) comb\n: ")
            if num == '1':
                self.task_name = 'cup'
            elif num == '2':
                self.task_name = 'door'
            else:
                print '\n!!!!!Invalid choice of task!!!!!\n'
                valid = False

            if valid:
                num=raw_input("Select actor:\n1) human \n2) robot\n: ")
                if num == '1':
                    self.actor = 'human'
                elif num == '2':
                    self.actor = 'robot'
                else:
                    print '\n!!!!!Invalid choice of actor!!!!!\n'
                    valid = False
            if valid:
                self.trial_name=raw_input("Enter trial's name (e.g. arm1, arm2): ")
                self.file_name = self.sub_name+'_'+self.task_name+'_'+self.actor+'_'+self.trial_name			
                ans=raw_input("Enter y to confirm that log file is:  "+self.file_name+"\n: ")
                if ans == 'y':
                    confirm = True
                    
    def init_log_file(self):
        self.task_cmd_input()
        ## self.tool_tip = tool_pose(self.tool_name,self.tflistener)
        self.ft = tool_ft(self.ft_sensor_topic_name)
        self.ft_log_file = open(self.file_name+'_ft.log','w')
        self.audio = tool_audio()
        self.audio_log_file = open(self.file_name+'_audio.log','w')        
        ## self.tool_tracker_log_file = open(self.file_name+'_tool_tracker.log','w')
        ## self.tooltip_log_file = open(self.file_name+'_tool_tip.log','w')
        ## self.head_tracker_log_file = open(self.file_name+'_head.log','w')
        ## self.gen_log_file = open(self.file_name+'_gen.log','w')
        self.pkl = self.file_name+'.pkl'

        raw_input('press Enter to reset')
        ## self.tool_tracker.set_origin()
        ## self.tool_tip.set_origin()
        ## self.head_tracker.set_origin()
        ## self.ft.reset()
        self.audio.reset()
        
        raw_input('press Enter to begin the test')
        self.init_time = rospy.get_time()
        ## self.head_tracker.init_time = self.init_time
        ## self.tool_tracker.init_time = self.init_time
        ## self.tool_tip.init_time = self.init_time
        self.ft.init_time = self.init_time

        ## print >> self.gen_log_file,'Begin_time',self.init_time,\
        ## 	'\nTime X Y Z Rotx Roty Rotz',\
        ## 	'\ntool_tracker_init_pos', self.tool_tracker.init_pos[0,0],\
        ## 			self.tool_tracker.init_pos[1,0],\
        ## 			self.tool_tracker.init_pos[2,0],\
        ## 	'\ntool_tracker_init_rot', self.tool_tracker.init_rot[0,0],\
        ## 			self.tool_tracker.init_rot[1,0],\
        ## 			self.tool_tracker.init_rot[2,0],\
        ## 	'\ntool_tip_init_pos', self.tool_tip.init_pos[0,0],\
        ## 			self.tool_tip.init_pos[1,0],\
        ## 			self.tool_tip.init_pos[2,0],\
        ## 	'\ntool_tip_init_rot', self.tool_tip.init_rot[0,0],\
        ## 			self.tool_tip.init_rot[1,0],\
        ## 			self.tool_tip.init_rot[2,0],\
        ## 	'\nhead_init_pos', self.head_tracker.init_pos[0,0],\
        ## 			self.head_tracker.init_pos[1,0],\
        ## 			self.head_tracker.init_pos[2,0],\
        ## 	'\nhead_init_rot', self.head_tracker.init_rot[0,0],\
        ## 			self.head_tracker.init_rot[1,0],\
        ## 			self.head_tracker.init_rot[2,0],\
        ## 	'\nTime Fx Fy Fz Fx_raw Fy_raw Fz_raw \
        ## 		Tx Ty Tz Tx_raw Ty_raw Tz_raw'
        
    def log_state(self, bias=True):
        ## self.head_tracker.log(self.head_tracker_log_file, log_delta_rot=True)
        ## self.tool_tracker.log(self.tool_tracker_log_file)
        ## self.tool_tip.log(self.tooltip_log_file)
        self.ft.log(self.ft_log_file)
        self.audio.log(self.audio_log_file)
        ## print '\nTool_Pos\t\tForce:\t\t\tHead_rot',\
        ## 	'\nX: ', self.tool_tracker.delta_pos[0,0],'\t',\
        ## 		self.ft.force[0,0],'\t',\
        ## 		math.degrees(self.head_tracker.delta_rot[0,0]),\
        ## 	'\nY: ', self.tool_tracker.delta_pos[1,0],'\t',\
        ## 		self.ft.force[1,0],'\t',\
        ## 		math.degrees(self.head_tracker.delta_rot[1,0]),\
        ## 	'\nZ: ', self.tool_tracker.delta_pos[2,0],'\t',\
        ## 		self.ft.force[2,0],'\t',\
        ## 		math.degrees(self.head_tracker.delta_rot[2,0])
        
    def close_log_file(self):
        # Finish data collection
        self.audio.close()
        
        d = {}
        d['init_time'] = self.init_time
        ## dict['init_pos'] = self.tool_tracker.init_pos
        ## dict['pos'] = self.tool_tracker.pos_data
        ## dict['quat'] = self.tool_tracker.quat_data
        ## dict['rot_data'] = self.tool_tracker.rot_data
        ## dict['ptime'] = self.tool_tracker.time_data

        ## dict['h_init_pos'] = self.head_tracker.init_pos
        ## dict['h_init_rot'] = self.head_tracker.init_rot
        ## dict['h_pos'] = self.head_tracker.pos_data
        ## dict['h_quat'] = self.head_tracker.quat_data
        ## dict['h_rot_data'] = self.head_tracker.rot_data
        ## dict['htime'] = self.head_tracker.time_data

        ## dict['tip_init_pos'] = self.tool_tip.init_pos
        ## dict['tip_init_rot'] = self.tool_tip.init_rot
        ## dict['tip_pos'] = self.tool_tip.pos_data
        ## dict['tip_quat'] = self.tool_tip.quat_data
        ## dict['tip_rot_data'] = self.tool_tip.rot_data
        ## dict['ttime'] = self.tool_tip.time_data

        ## dict['force'] = self.ft.force_data
        d['force_raw'] = self.ft.force_raw_data
        ## dict['torque'] = self.ft.torque_data
        d['torque_raw'] = self.ft.torque_raw_data
        d['ftime'] = self.ft.time_data
        ut.save_pickle(d, self.pkl)

        self.ft_log_file.close()
        ## self.tool_tracker_log_file.close()
        ## self.tooltip_log_file.close()
        ## self.head_tracker_log_file.close()
        ## self.gen_log_file.close()
        print 'Closing..  log files have saved..'

                

if __name__ == '__main__':

    audio = tool_audio()
    audio.reset()


    
    ## log = ADL_log()
    ## log.init_log_file()

    ## while not rospy.is_shutdown():
    ##     log.log_state()
    ##     rospy.sleep(1/1000.)

    ## log.close_log_file()
    

    






## class adl_recording():
##     def __init__(self, obj_id_list, netft_flag_list):
##         self.ftc_list = []                                                                                       
##         for oid, netft in zip(obj_id_list, netft_flag_list):                                                     
##             self.ftc_list.append(ftc.FTClient(oid, netft))                                                       
##         self.oid_list = copy.copy(obj_id_list)
        
##         ## self.initComms()
##         pass

        
##     def initComms(self):
        
##         # service
##         #rospy.Service('door_opening/mech_analyse_enable', None_Bool, self.mech_anal_en_cb)
        
##         # Subscriber
##         rospy.Subscriber('/netft_rdt', Wrench, self.ft_sensor_cb)                    

        
##     # returns a dict of <object id: 3x1 np matrix of force>
##     def get_forces(self, bias = True):
##         f_list = []
##         for i, ft_client in enumerate(self.ftc_list):
##             f = ft_client.read(without_bias = not bias)
##             f = f[0:3, :]

##             ## trans, quat = self.tf_lstnr.lookupTransform('/torso_lift_link',
##             ##                                             self.oid_list[i],
##             ##                                             rospy.Time(0))
##             ## rot = tr.quaternion_to_matrix(quat)
##             ## f = rot * f
##             f_list.append(-f)

##         return dict(zip(self.oid_list, f_list))


##     def bias_fts(self):
##         for ftcl in self.ftc_list:
##             ftcl.bias()
        
        
##     # TODO
##     def ft_sensor_cb(self, msg):

##         with self.ft_lock:
##             self.ft_data = [msg.force.x, msg.force.y, msg.force.z] # tool frame

##             # need to convert into torso frame?


##     def start(self, bManual=False):
##         rospy.loginfo("ADL Online Recording Start")

##         ar.bias_fts()
##         rospy.loginfo("FT bias complete")

        
##         rate = rospy.Rate(2) # 25Hz, nominally.
##         rospy.loginfo("Beginning publishing waypoints")
##         while not rospy.is_shutdown():         
##             f = self.get_forces()[0]
##             print f
##             #print rospy.Time()
##             rate.sleep()        
            
    
