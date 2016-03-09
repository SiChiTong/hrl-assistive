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

# system
import os, sys, copy
import random

# util
import numpy as np
import scipy
import hrl_lib.util as ut
import hrl_lib.quaternion as qt
from hrl_anomaly_detection import util

from mvpa2.datasets.base import Dataset
from mvpa2.generators.partition import NFoldPartitioner
from mvpa2.generators import splitters

from sklearn import cross_validation

import matplotlib.pyplot as plt

def create_mvpa_dataset(aXData, chunks, labels):
    data = Dataset(samples=aXData)
    data.sa['id']      = range(0,len(labels))
    data.sa['chunks']  = chunks
    data.sa['targets'] = labels

    return data

def kFold_data_index(nAbnormal, nNormal, nAbnormalFold, nNormalFold):

    normal_folds   = cross_validation.KFold(nNormal, n_folds=nNormalFold, shuffle=True)
    abnormal_folds = cross_validation.KFold(nAbnormal, n_folds=nAbnormalFold, shuffle=True)

    kFold_list = []

    for normal_temp_fold, normal_test_fold in normal_folds:

        normal_dc_fold = cross_validation.KFold(len(normal_temp_fold), \
                                                n_folds=nNormalFold-1, shuffle=True)
        for normal_train_fold, normal_classifier_fold in normal_dc_fold:

            normal_d_fold = normal_temp_fold[normal_train_fold]
            normal_c_fold = normal_temp_fold[normal_classifier_fold]

            for abnormal_c_fold, abnormal_test_fold in abnormal_folds:
                '''
                Normal training data for model
                Normal training data 
                Abnormal training data 
                Normal test data 
                Abnormal test data 
                '''
                index_list = [normal_d_fold, normal_c_fold, abnormal_c_fold, \
                              normal_test_fold, abnormal_test_fold]
                kFold_list.append(index_list)

    return kFold_list

def kFold_data_index2(nNormal, nAbnormal, nNormalFold, nAbnormalFold ):
    '''
    Output:
    Normal training data 
    Abnormal training data 
    Normal test data 
    Abnormal test data 
    '''

    normal_folds   = cross_validation.KFold(nNormal, n_folds=nNormalFold, shuffle=True)
    abnormal_folds = cross_validation.KFold(nAbnormal, n_folds=nAbnormalFold, shuffle=True)

    kFold_list = []

    for normal_train_fold, normal_test_fold in normal_folds:

        for abnormal_train_fold, abnormal_test_fold in abnormal_folds:
            index_list = [normal_train_fold, abnormal_train_fold, \
                          normal_test_fold, abnormal_test_fold]
            kFold_list.append(index_list)

    return kFold_list


#-------------------------------------------------------------------------------------------------
def getDataSet(subject_names, task_name, raw_data_path, processed_data_path, rf_center, local_range, \
               downSampleSize=200, scale=10.0, ae_data=False, data_ext=True, \
               nAugment=0,\
               success_viz=False, failure_viz=False, \
               save_pdf=False, solid_color=True, \
               feature_list=['crossmodal_targetEEDist'], data_renew=False):
    '''
    ae_data: Auto-encoder data
    '''

    if os.path.isdir(processed_data_path) is False:
        os.system('mkdir -p '+processed_data_path)

    if ae_data:
        save_pkl = os.path.join(processed_data_path, 'ae_feature_extraction_'+rf_center+'_'+str(local_range) )
    else:
        save_pkl = os.path.join(processed_data_path, 'feature_extraction_'+rf_center+'_'+str(local_range) )
            
    if os.path.isfile(save_pkl) and data_renew is not True :
        print "--------------------------------------"
        print "Load saved data"
        print "--------------------------------------"
        data_dict = ut.load_pickle(save_pkl)
        allData         = data_dict['allData']
        successData     = data_dict['trainingData'] 
        failureData     = data_dict['abnormalTestData']
        aug_successData = data_dict.get('successData_augmented', [])
        aug_failureData = data_dict.get('failureData_augmented', [])
        failureNameList = data_dict['abnormalTestNameList']
        param_dict      = data_dict['param_dict']
    else:
        ## data_renew = False #temp        
        success_list, failure_list = util.getSubjectFileList(raw_data_path, subject_names, task_name)

        # loading and time-sync    
        all_data_pkl     = os.path.join(processed_data_path, task_name+'_all_'+rf_center+\
                                        '_'+str(local_range))
        _, all_data_dict = util.loadData(success_list+failure_list, isTrainingData=False,
                                         downSampleSize=downSampleSize,\
                                         local_range=local_range, rf_center=rf_center,\
                                         ##global_data=True,\
                                         renew=data_renew, save_pkl=all_data_pkl)

        # data set
        if ae_data is False:

            success_data_pkl     = os.path.join(processed_data_path, task_name+'_success_'+rf_center+\
                                                '_'+str(local_range))
            _, success_data_dict = util.loadData(success_list, isTrainingData=True,
                                                 downSampleSize=downSampleSize,\
                                                 local_range=local_range, rf_center=rf_center,\
                                                 renew=data_renew, save_pkl=success_data_pkl)

            failure_data_pkl     = os.path.join(processed_data_path, task_name+'_failure_'+rf_center+\
                                                '_'+str(local_range))
            _, failure_data_dict = util.loadData(failure_list, isTrainingData=False,
                                                 downSampleSize=downSampleSize,\
                                                 local_range=local_range, rf_center=rf_center,\
                                                 renew=data_renew, save_pkl=failure_data_pkl)
            
            allData, param_dict = extractFeature(all_data_dict, feature_list, scale=scale)
            successData, _      = extractFeature(success_data_dict, feature_list, scale=scale, \
                                                 param_dict=param_dict)
            failureData, _      = extractFeature(failure_data_dict, feature_list, scale=scale, \
                                                 param_dict=param_dict)
            aug_successData = []
            aug_failureData = []
        else:
            successData, failureData, aug_successData, aug_failureData, param_dict = \
              extractRawData(all_data_dict, feature_list, nSuccess=len(success_list), nFailure=len(failure_list),\
                             nAugment=nAugment)
            allData = None #successData+failureData
                                                                    
        data_dict = {}
        data_dict['allData']              = allData = np.array(allData)
        data_dict['trainingData']         = successData = np.array(successData)
        data_dict['abnormalTestData']     = failureData = np.array(failureData)
        data_dict['abnormalTestNameList'] = failureNameList = None #failure_data_dict['fileNameList']
        data_dict['successData_augmented'] = aug_successData = np.array(aug_successData)
        data_dict['failureData_augmented'] = aug_failureData = np.array(aug_failureData)
        data_dict['param_dict'] = param_dict
        ut.save_pickle(data_dict, save_pkl)

    
    ## All data
    nPlot = None

    if data_ext:
        feature_names = np.array(param_dict['feature_names'])

        # 1) exclude stationary data
        thres = 0.025
        n,m,k = np.shape(successData)
        diff_all_data = successData[:,:,1:] - successData[:,:,:-1]
        add_idx    = []
        remove_idx = []
        std_list = []
        for i in xrange(n):
            std = np.max(np.max(diff_all_data[i], axis=1))
            std_list.append(std)
            if  std < thres: remove_idx.append(i)
            else: add_idx.append(i)

        allData          = allData[add_idx]
        successData      = successData[add_idx]
        failureData      = failureData[add_idx]
        AddFeature_names    = feature_names[add_idx]
        RemoveFeature_names = feature_names[remove_idx]

        print "--------------------------------"
        print "STD list: ", std_list
        print "Add features: ", AddFeature_names
        print "Remove features: ", RemoveFeature_names
        print "--------------------------------"
        ## sys.exit()


    # -------------------- Display ---------------------
    fig = None
    if success_viz:
        feature_names = np.array(param_dict['feature_names'])

        fig = plt.figure()
        n,m,k = np.shape(successData)
        if nPlot is None:
            if n%2==0: nPlot = n
            else: nPlot = n+1

        for i in xrange(n):
            ax = fig.add_subplot((nPlot/2)*100+20+i)
            if solid_color: ax.plot(successData[i].T, c='b')
            else: ax.plot(successData[i].T)
            ax.set_title( AddFeature_names[i] )

    if failure_viz:
        feature_names = np.array(param_dict['feature_names'])
        if fig is None: fig = plt.figure()
        n,m,k = np.shape(failureData)
        if nPlot is None:
            if n%2==0: nPlot = n
            else: nPlot = n+1

        for i in xrange(n):
            ax = fig.add_subplot((nPlot/2)*100+20+i)
            if solid_color: ax.plot(failureData[i].T, c='r')
            else: ax.plot(failureData[i].T)
            ax.set_title( AddFeature_names[i] )

    if success_viz or failure_viz:
        feature_names = np.array(param_dict['feature_names'])
        plt.tight_layout(pad=3.0, w_pad=0.5, h_pad=0.5)

        if save_pdf:
            fig.savefig('test.pdf')
            fig.savefig('test.png')
            os.system('cp test.p* ~/Dropbox/HRL/')        
        else:
            plt.show()

    print "---------------------------------------------------"
    print "s/f data: ", np.shape(successData), np.shape(failureData)
    print "augmented s/f data: ", np.shape(aug_successData), np.shape(aug_failureData)
    print "---------------------------------------------------"

    if ae_data:
        return successData, failureData, aug_successData, aug_failureData, param_dict
    else:
        return allData, successData, failureData, failureNameList, param_dict


def getAEdataSet(idx, successData, failureData, \
                 normalTrainIdx, abnormalTrainIdx, normalTestIdx, abnormalTestIdx,
                 time_window, \
                 AE_proc_data, \
                 # data param
                 processed_data_path, \
                 # AE param
                 layer_sizes=[256,128,16], learning_rate=1e-6, learning_rate_decay=1e-6, \
                 momentum=1e-6, dampening=1e-6, lambda_reg=1e-6, \
                 max_iteration=20000, min_loss=1.0, cuda=False, \
                 verbose=False, renew=False ):

    if os.path.isfile(AE_proc_data) and not renew:
        d = ut.load_pickle(AE_proc_data)
        return d

    from hrl_anomaly_detection.feature_extractors import auto_encoder as ae
    AE_model = os.path.join(processed_data_path, 'ae_model_'+str(idx)+'.pkl')

    # dim x sample x length
    normalTrainData   = successData[:, normalTrainIdx, :] 
    abnormalTrainData = failureData[:, abnormalTrainIdx, :] 
    normalTestData    = successData[:, normalTestIdx, :] 
    abnormalTestData  = failureData[:, abnormalTestIdx, :]

    normalTrainData   = np.swapaxes(normalTrainData, 0, 1)
    abnormalTrainData = np.swapaxes(abnormalTrainData, 0, 1)
    normalTestData    = np.swapaxes(normalTestData, 0, 1)
    abnormalTestData  = np.swapaxes(abnormalTestData, 0, 1)


    # sample x time_window_flatten_length
    new_normalTrainData   = getTimeDelayData(normalTrainData, time_window)
    new_abnormalTrainData = getTimeDelayData(abnormalTrainData, time_window)
    new_normalTestData    = getTimeDelayData(normalTestData, time_window)
    new_abnormalTestData  = getTimeDelayData(abnormalTestData, time_window)
    nSingleData           = len(normalTrainData[0][0])-time_window+1
    nDim                  = len(new_normalTrainData[1])

    # sample x time_window_flatten_length
    X_train  = np.vstack([new_normalTrainData, new_abnormalTrainData])
    
    # train ae
    ml = ae.auto_encoder([nDim]+layer_sizes, \
                         learning_rate, learning_rate_decay, momentum, dampening, \
                         lambda_reg, time_window, \
                         max_iteration=max_iteration, min_loss=min_loss, cuda=cuda, verbose=verbose)

    if os.path.isfile(AE_model):
        ml.load_params(AE_model)
    else:
        ml.fit(X_train)
        ml.save_params(AE_model)


    def predictFeatures(clf, X, nSingleData):
        # Generate training features
        feature_list = []
        for idx in xrange(0, len(X), nSingleData):
            test_features = clf.predict_features( X[idx:idx+nSingleData,:].astype('float32') )
            feature_list.append(test_features)
        return feature_list

    # test ae
    # sample x dim => dim x sample
    d = {}
    d['normTrainData']   = np.swapaxes(predictFeatures(ml, new_normalTrainData, nSingleData), 0,1)
    d['abnormTrainData'] = np.swapaxes(predictFeatures(ml, new_abnormalTrainData, nSingleData), 0,1) 
    d['normTestData']    = np.swapaxes(predictFeatures(ml, new_normalTestData, nSingleData), 0,1)
    d['abnormTestData']  = np.swapaxes(predictFeatures(ml, new_abnormalTestData, nSingleData), 0,1)
    ut.save_pickle(d, AE_proc_data)

    return d


def variancePooling(X, param_dict):
    '''
    dim x samples
    TODO: can we select final dimension?
    '''
    dim         = param_dict['dim']
    min_all_std = param_dict['min_all_std']
    max_avg_std = param_dict['max_avg_std']

    if 'dim_idx' not in param_dict.keys():
        dim_idx = []
        new_X   = []

        std_list = []
        for i in xrange(len(X)):
            # for each dimension
            ## avg_std = np.mean( np.std(X[i], axis=0) )
            std_avg = np.std( np.mean(X[i], axis=0) )
            ## std_list.append(std_avg/avg_std)
            std_list.append(std_avg)

        indices = np.argsort(std_list)[::-1]

        for idx in indices[:dim]:
            new_X.append(X[idx])
            dim_idx.append(idx)

            ## if all_std > min_all_std and avg_ea_std < max_avg_std:
            ##     new_X.append(X[i])
            ##     dim_idx.append(i)

        param_dict['dim_idx'] = dim_idx
    else:
        new_X = [ X[idx] for idx in param_dict['dim_idx'] ]

    return np.array(new_X), param_dict
        
    
#-------------------------------------------------------------------------------------------------

def extractFeature(d, feature_list, scale=10.0, param_dict=None, verbose=False):

    if param_dict is None:
        isTrainingData=True
        param_dict = {}

        if 'unimodal_audioPower' in feature_list:
            ## power_max = np.amax(d['audioPowerList'])
            ## power_min = np.amin(d['audioPowerList'])
            ## power_min = np.mean(np.array(d['audioPowerList'])[:,:10])
            power_min = 10000
            power_max = 0
            for pwr in d['audioPowerList']:
                p_min = np.amin(pwr)
                p_max = np.amax(pwr)
                if power_min > p_min:
                    power_min = p_min
                ## if p_max < 50 and power_max < p_max:
                if power_max < p_max:
                    power_max = p_max

            param_dict['unimodal_audioPower_power_max'] = power_max
            param_dict['unimodal_audioPower_power_min'] = power_min
                                
        ## if 'unimodal_ftForce' in feature_list:
        ##     force_array = None
        ##     start_force_array = None
        ##     for idx in xrange(len(d['ftForceList'])):
        ##         if force_array is None:
        ##             force_array = d['ftForceList'][idx]
        ##             ## start_force_array = d['ftForceList'][idx][:,:5]
        ##         else:
        ##             force_array = np.hstack([force_array, d['ftForceList'][idx] ])
        ##             ## start_force_array = np.hstack([start_force_array, d['ftForceList'][idx][:,:5]])

        ##     ftPCADim    = 2
        ##     ftForce_pca = PCA(n_components=ftPCADim)
        ##     res = ftForce_pca.fit_transform( force_array.T )            
        ##     param_dict['unimodal_ftForce_pca'] = ftForce_pca
        ##     param_dict['unimodal_ftForce_pca_dim'] = ftPCADim

        ##     ## res = ftForce_pca.transform(start_force_array.T)
        ##     ## param_dict['unimodal_ftForce_pca_init_avg'] = np.array([np.mean(res, axis=0)]).T
        ##     ## param_dict['unimodal_ftForce_init_avg'] = np.mean(start_force_array, axis=1)

        if 'unimodal_ppsForce' in feature_list:
            ppsLeft  = d['ppsLeftList']
            ppsRight = d['ppsRightList']

            pps_mag = []
            for i in xrange(len(ppsLeft)):                
                pps      = np.vstack([ppsLeft[i], ppsRight[i]])
                pps_mag.append( np.linalg.norm(pps, axis=0) )

            pps_max = np.max( np.array(pps_mag).flatten() )
            pps_min = np.min( np.array(pps_mag).flatten() )
            param_dict['unimodal_ppsForce_max'] = pps_max
            param_dict['unimodal_ppsForce_min'] = pps_min

        param_dict['feature_names'] = []
    else:
        isTrainingData=False
            

    # -------------------------------------------------------------        

    # extract local features
    dataList   = []
    for idx in xrange(len(d['timesList'])): # each sample

        timeList     = d['timesList'][idx]
        dataSample = None

        # Unimoda feature - Audio --------------------------------------------
        if 'unimodal_audioPower' in feature_list:
            ## audioAzimuth = d['audioAzimuthList'][idx]
            audioPower   = d['audioPowerList'][idx]            
            unimodal_audioPower = audioPower
            
            if dataSample is None: dataSample = copy.copy(np.array(unimodal_audioPower))
            else: dataSample = np.vstack([dataSample, copy.copy(unimodal_audioPower)])
            if 'audioPower' not in param_dict['feature_names']:
                param_dict['feature_names'].append('audioPower')

        # Unimoda feature - AudioWrist ---------------------------------------
        if 'unimodal_audioWristRMS' in feature_list:
            audioWristRMS = d['audioWristRMSList'][idx]            
            unimodal_audioWristRMS = audioWristRMS
            
            if dataSample is None: dataSample = copy.copy(np.array(unimodal_audioWristRMS))
            else: dataSample = np.vstack([dataSample, copy.copy(unimodal_audioWristRMS)])
            if 'audioWristRMS' not in param_dict['feature_names']:
                param_dict['feature_names'].append('audioWristRMS')

        # Unimodal feature - Kinematics --------------------------------------
        if 'unimodal_kinVel' in feature_list:
            kinVel  = d['kinVelList'][idx]
            unimodal_kinVel = kinVel

            if dataSample is None: dataSample = np.array(unimodal_kinVel)
            else: dataSample = np.vstack([dataSample, unimodal_kinVel])
            if 'kinVel_x' not in param_dict['feature_names']:
                param_dict['feature_names'].append('kinVel_x')
                param_dict['feature_names'].append('kinVel_y')
                param_dict['feature_names'].append('kinVel_z')

        # Unimodal feature - Force -------------------------------------------
        if 'unimodal_ftForce' in feature_list:
            ftForce = d['ftForceList'][idx]

            # magnitude
            if len(np.shape(ftForce)) > 1:
                unimodal_ftForce_mag = np.linalg.norm(ftForce, axis=0)
                # individual force
                unimodal_ftForce_ind = ftForce[2:3,:]                
                
                if dataSample is None: dataSample = np.array(unimodal_ftForce_mag)
                else: dataSample = np.vstack([dataSample, unimodal_ftForce_mag])

                if dataSample is None: dataSample = np.array(unimodal_ftForce_ind)
                else: dataSample = np.vstack([dataSample, unimodal_ftForce_ind])

                if 'ftForce_z' not in param_dict['feature_names']:
                    param_dict['feature_names'].append('ftForce_mag')
                    ## param_dict['feature_names'].append('ftForce_x')
                    ## param_dict['feature_names'].append('ftForce_y')
                    param_dict['feature_names'].append('ftForce_z')
            else:                
                unimodal_ftForce_mag = ftForce
            
                if dataSample is None: dataSample = np.array(unimodal_ftForce_mag)
                else: dataSample = np.vstack([dataSample, unimodal_ftForce_mag])

                if 'ftForce_mag' not in param_dict['feature_names']:
                    param_dict['feature_names'].append('ftForce_mag')

            ## ftPos   = d['kinEEPosList'][idx]
            ## ftForce_pca = param_dict['unimodal_ftForce_pca']

            ## unimodal_ftForce = None
            ## for time_idx in xrange(len(timeList)):
            ##     if unimodal_ftForce is None:
            ##         unimodal_ftForce = ftForce_pca.transform(ftForce[:,time_idx:time_idx+1].T).T
            ##     else:
            ##         unimodal_ftForce = np.hstack([ unimodal_ftForce, \
            ##                                        ftForce_pca.transform(ftForce[:,time_idx:time_idx+1].T).T ])

            ## unimodal_ftForce -= np.array([np.mean(unimodal_ftForce[:,:5], axis=1)]).T
            
            ## if 'ftForce_1' not in param_dict['feature_names']:
            ##     param_dict['feature_names'].append('ftForce_1')
            ##     param_dict['feature_names'].append('ftForce_2')
            ## if 'ftForce_x' not in param_dict['feature_names']:
            ##     param_dict['feature_names'].append('ftForce_x')
            ##     param_dict['feature_names'].append('ftForce_y')
            ##     param_dict['feature_names'].append('ftForce_z')

        # Unimodal feature - pps -------------------------------------------
        if 'unimodal_ppsForce' in feature_list:
            ppsLeft  = d['ppsLeftList'][idx]
            ppsRight = d['ppsRightList'][idx]
            ppsPos   = d['kinTargetPosList'][idx]

            pps = np.vstack([ppsLeft, ppsRight])
            unimodal_ppsForce = pps

            # 2
            pps = np.vstack([np.sum(ppsLeft, axis=0), np.sum(ppsRight, axis=0)])
            unimodal_ppsForce = pps
            
            # 1
            ## unimodal_ppsForce = np.array([np.linalg.norm(pps, axis=0)])

            unimodal_ppsForce -= np.array([np.mean(unimodal_ppsForce[:,:5], axis=1)]).T

            ## unimodal_ppsForce = []
            ## for time_idx in xrange(len(timeList)):
            ##     unimodal_ppsForce.append( np.linalg.norm(pps[:,time_idx]) )

            if dataSample is None: dataSample = unimodal_ppsForce
            else: dataSample = np.vstack([dataSample, unimodal_ppsForce])

            ## if 'ppsForce' not in param_dict['feature_names']:
            ##     param_dict['feature_names'].append('ppsForce')
            if 'ppsForce_1' not in param_dict['feature_names']:
                param_dict['feature_names'].append('ppsForce_1')
                param_dict['feature_names'].append('ppsForce_2')                
            ## if 'ppsForce_1' not in param_dict['feature_names']:
            ##     param_dict['feature_names'].append('ppsForce_1')
            ##     param_dict['feature_names'].append('ppsForce_2')
            ##     param_dict['feature_names'].append('ppsForce_3')
            ##     param_dict['feature_names'].append('ppsForce_4')
            ##     param_dict['feature_names'].append('ppsForce_5')
            ##     param_dict['feature_names'].append('ppsForce_6')


        # Unimodal feature - vision change ------------------------------------
        if 'unimodal_visionChange' in feature_list:
            visionChangeMag = d['visionChangeMagList'][idx]

            unimodal_visionChange = visionChangeMag

            if dataSample is None: dataSample = unimodal_visionChange
            else: dataSample = np.vstack([dataSample, unimodal_visionChange])
            if 'visionChange' not in param_dict['feature_names']:
                param_dict['feature_names'].append('visionChange')

                
        # Unimodal feature - fabric skin ------------------------------------
        if 'unimodal_fabricForce' in feature_list:
            fabricMag = d['fabricMagList'][idx]

            unimodal_fabricForce = fabricMag

            if dataSample is None: dataSample = unimodal_fabricForce
            else: dataSample = np.vstack([dataSample, unimodal_fabricForce])
            if 'fabricForce' not in param_dict['feature_names']:
                param_dict['feature_names'].append('fabricForce')

            
        # Crossmodal feature - relative dist --------------------------
        if 'crossmodal_targetEEDist' in feature_list:
            kinEEPos     = d['kinEEPosList'][idx]
            kinTargetPos  = d['kinTargetPosList'][idx]

            dist = np.linalg.norm(kinTargetPos - kinEEPos, axis=0)
            crossmodal_targetEEDist = []
            for time_idx in xrange(len(timeList)):
                crossmodal_targetEEDist.append( dist[time_idx])

            if dataSample is None: dataSample = np.array(crossmodal_targetEEDist)
            else: dataSample = np.vstack([dataSample, crossmodal_targetEEDist])
            if 'targetEEDist' not in param_dict['feature_names']:
                param_dict['feature_names'].append('targetEEDist')


        # Crossmodal feature - relative angle --------------------------
        if 'crossmodal_targetEEAng' in feature_list:                
            kinEEQuat    = d['kinEEQuatList'][idx]
            kinTargetQuat = d['kinTargetQuatList'][idx]

            ## kinEEPos     = d['kinEEPosList'][idx]
            ## kinTargetPos = d['kinTargetPosList'][idx]
            ## dist         = np.linalg.norm(kinTargetPos - kinEEPos, axis=0)
            
            crossmodal_targetEEAng = []
            for time_idx in xrange(len(timeList)):

                startQuat = kinEEQuat[:,time_idx]
                endQuat   = kinTargetQuat[:,time_idx]

                diff_ang = qt.quat_angle(startQuat, endQuat)
                crossmodal_targetEEAng.append( abs(diff_ang) )

            ## fig = plt.figure()
            ## ## plt.plot(crossmodal_targetEEAng)
            ## plt.plot( kinEEQuat[0] )
            ## plt.plot( kinEEQuat[1] )
            ## plt.plot( kinEEQuat[2] )
            ## plt.plot( kinEEQuat[3] )
            ## fig.savefig('test.pdf')
            ## fig.savefig('test.png')
            ## os.system('cp test.p* ~/Dropbox/HRL/')        
            ## sys.exit()
            
            if dataSample is None: dataSample = np.array(crossmodal_targetEEAng)
            else: dataSample = np.vstack([dataSample, crossmodal_targetEEAng])
            if 'targetEEAng' not in param_dict['feature_names']:
                param_dict['feature_names'].append('targetEEAng')

        # Crossmodal feature - vision relative dist with main(first) vision target----
        if 'crossmodal_artagEEDist' in feature_list:
            kinEEPos  = d['kinEEPosList'][idx]
            visionArtagPos = d['visionArtagPosList'][idx][:3] # originally length x 3*tags

            dist = np.linalg.norm(visionArtagPos - kinEEPos, axis=0)
            crossmodal_artagEEDist = []
            for time_idx in xrange(len(timeList)):
                crossmodal_artagEEDist.append(dist[time_idx])

            if dataSample is None: dataSample = np.array(crossmodal_artagEEDist)
            else: dataSample = np.vstack([dataSample, crossmodal_artagEEDist])
            if 'artagEEDist' not in param_dict['feature_names']:
                param_dict['feature_names'].append('artagEEDist')

        # Crossmodal feature - vision relative angle --------------------------
        if 'crossmodal_artagEEAng' in feature_list:                
            kinEEQuat    = d['kinEEQuatList'][idx]
            visionArtagQuat = d['visionArtagQuatList'][idx][:4]

            kinEEPos  = d['kinEEPosList'][idx]
            visionArtagPos = d['visionArtagPosList'][idx][:3]
            dist = np.linalg.norm(visionArtagPos - kinEEPos, axis=0)
            
            crossmodal_artagEEAng = []
            for time_idx in xrange(len(timeList)):

                startQuat = kinEEQuat[:,time_idx]
                endQuat   = visionArtagQuat[:,time_idx]

                diff_ang = qt.quat_angle(startQuat, endQuat)
                crossmodal_artagEEAng.append( abs(diff_ang) )

            if dataSample is None: dataSample = np.array(crossmodal_artagEEAng)
            else: dataSample = np.vstack([dataSample, crossmodal_artagEEAng])
            if 'artagEEAng' not in param_dict['feature_names']:
                param_dict['feature_names'].append('artagEEAng')

        # ----------------------------------------------------------------
        dataList.append(dataSample)


    # Convert data structure & cut unnecessary part
    # From nSample x dim x length
    # To dim x nSample x length
    nSample      = len(dataList)
    nEmissionDim = len(dataList[0])
    features = np.swapaxes(dataList, 0, 1)    

    # Scaling ------------------------------------------------------------
    if isTrainingData:
        param_dict['feature_max'] = [ np.max(np.array(feature).flatten()) for feature in features ]
        param_dict['feature_min'] = [ np.min(np.array(feature).flatten()) for feature in features ]
        print "Before scaling, max is: ", param_dict['feature_max']
        print "Before scaling, min is: ", param_dict['feature_min']
        
        
    scaled_features = []
    for i, feature in enumerate(features):

        if abs( param_dict['feature_max'][i] - param_dict['feature_min'][i]) < 1e-3:
            scaled_features.append( np.array(feature) )
        else:
            scaled_features.append( scale* ( np.array(feature) - param_dict['feature_min'][i] )\
                                    /( param_dict['feature_max'][i] - param_dict['feature_min'][i]) )

    return scaled_features, param_dict


def extractRawData(d, raw_feature_list, nSuccess, nFailure, param_dict=None, nAugment=1, verbose=False):

    from sandbox_dpark_darpa_m3.lib import hrl_dh_lib as dh
    from hrl_lib import quaternion as qt
    
    if param_dict is None:
        isTrainingData=True
        param_dict = {}
    else:
        isTrainingData=False
            

    # -------------------------------------------------------------        
    # extract modality data
    dataList = []
    dataDim  = []
    nSample  = len(d['timesList'])
    for idx in xrange(nSample): # each sample

        timeList     = d['timesList'][idx]
        dataSample = None

        # main-artag EE - vision relative dist with main(first) vision target----
        if 'relativePose_artag_EE' in raw_feature_list:
            kinEEPos        = d['kinEEPosList'][idx]
            kinEEQuat       = d['kinEEQuatList'][idx]
            visionArtagPos  = d['visionArtagPosList'][idx][:3] # originally length x 3*tags
            visionArtagQuat = d['visionArtagQuatList'][idx][:4] # originally length x 3*tags

            # pos and quat?
            relativePose = []
            for time_idx in xrange(len(timeList)):
                startFrame = dh.array2KDLframe( visionArtagPos[:,time_idx].tolist() +\
                                                visionArtagQuat[:,time_idx].tolist() )
                endFrame   = dh.array2KDLframe( kinEEPos[:,time_idx].tolist()+\
                                                kinEEQuat[:,time_idx].tolist() )
                diffFrame  = endFrame*startFrame.Inverse()                                
                relativePose.append( dh.KDLframe2List(diffFrame) )

            relativePose = np.array(relativePose).T[:-1]
            
            if dataSample is None: dataSample = relativePose
            else: dataSample = np.vstack([dataSample, relativePose])
            if idx == 0: dataDim.append(['relativePose_artag_EE', len(relativePose)])
                

        # main-artag sub-artag - vision relative dist with main(first) vision target----
        if 'relativePose_artag_artag' in raw_feature_list:
            visionArtagPos1 = d['visionArtagPosList'][idx][:3] # originally length x 3*tags
            visionArtagQuat1 = d['visionArtagQuatList'][idx][:4] # originally length x 3*tags
            visionArtagPos2 = d['visionArtagPosList'][idx][3:6] # originally length x 3*tags
            visionArtagQuat2 = d['visionArtagQuatList'][idx][4:8] # originally length x 3*tags

            # pos and quat?
            relativePose = []
            for time_idx in xrange(len(timeList)):

                startFrame = dh.array2KDLframe( visionArtagPos1[:,time_idx].tolist() +\
                                                visionArtagQuat1[:,time_idx].tolist() )
                endFrame = dh.array2KDLframe( visionArtagPos2[:,time_idx].tolist() +\
                                              visionArtagQuat2[:,time_idx].tolist() )                
                diffFrame  = endFrame*startFrame.Inverse()                                
                relativePose.append( dh.KDLframe2List(diffFrame) )

            relativePose = np.array(relativePose).T[:-1]

            if dataSample is None: dataSample = relativePose
            else: dataSample = np.vstack([dataSample, relativePose])
            if idx == 0: dataDim.append(['relativePose_artag_artag', len(relativePose)])


        # Audio --------------------------------------------
        if 'kinectAudio' in raw_feature_list:
            audioPower   = d['audioPowerList'][idx]                        
            if dataSample is None: dataSample = copy.copy(np.array(audioPower))
            else: dataSample = np.vstack([dataSample, copy.copy(audioPower)])
            if idx == 0: dataDim.append(['kinectAudio', len(audioPower)])

        # AudioWrist ---------------------------------------
        if 'wristAudio' in raw_feature_list:
            audioWristRMS  = d['audioWristRMSList'][idx]
            audioWristMFCC = d['audioWristMFCCList'][idx]            

            if dataSample is None: dataSample = copy.copy(np.array(audioWristRMS))
            else: dataSample = np.vstack([dataSample, copy.copy(audioWristRMS)])

            dataSample = np.vstack([dataSample, copy.copy(audioWristMFCC)])
            if idx == 0: dataDim.append(['wristAudio', len(audioWristRMS)+len(audioWristMFCC)])                

        # FT -------------------------------------------
        if 'ft' in raw_feature_list:
            ftForce  = d['ftForceList'][idx]
            ftTorque = d['ftTorqueList'][idx]

            if dataSample is None: dataSample = np.array(ftForce)
            else: dataSample = np.vstack([dataSample, ftForce])

            if dataSample is None: dataSample = np.array(ftTorque)
            else: dataSample = np.vstack([dataSample, ftTorque])
            if idx == 0: dataDim.append(['ft', len(ftForce)+len(ftTorque)])

        # pps -------------------------------------------
        if 'pps' in raw_feature_list:
            ppsLeft  = d['ppsLeftList'][idx]
            ppsRight = d['ppsRightList'][idx]

            if dataSample is None: dataSample = ppsLeft
            else: dataSample = np.vstack([dataSample, ppsLeft])

            if dataSample is None: dataSample = ppsRight
            else: dataSample = np.vstack([dataSample, ppsRight])
            if idx == 0: dataDim.append(['pps', len(ppsLeft)+len(ppsRight)])

        # Kinematics --------------------------------------
        if 'kinematics' in raw_feature_list:
            kinEEPos   = d['kinEEPosList'][idx]
            kinEEQuat  = d['kinEEQuatList'][idx]
            kinJntPos  = d['kinJntPosList'][idx]
            kinPos     = d['kinPosList'][idx]
            kinVel     = d['kinVelList'][idx]

            if dataSample is None: dataSample = np.array(kinEEPos)
            else: dataSample = np.vstack([dataSample, kinEEPos])
            if 'kinEEPos_x' not in param_dict['feature_names']:
                param_dict['feature_names'].append('kinEEPos_x')
                param_dict['feature_names'].append('kinEEPos_y')
                param_dict['feature_names'].append('kinEEPos_z')

            if dataSample is None: dataSample = np.array(kinEEQuat)
            else: dataSample = np.vstack([dataSample, kinEEQuat])
            if 'kinEEQuat_x' not in param_dict['feature_names']:
                param_dict['feature_names'].append('kinEEQuat_x')
                param_dict['feature_names'].append('kinEEQuat_y')
                param_dict['feature_names'].append('kinEEQuat_z')
                param_dict['feature_names'].append('kinEEQuat_w')

            if dataSample is None: dataSample = np.array(kinJntPos)
            else: dataSample = np.vstack([dataSample, kinJntPos])
            if 'kinJntPos_1' not in param_dict['feature_names']:
                param_dict['feature_names'].append('kinJntPos_1')
                param_dict['feature_names'].append('kinJntPos_2')
                param_dict['feature_names'].append('kinJntPos_3')
                param_dict['feature_names'].append('kinJntPos_4')
                param_dict['feature_names'].append('kinJntPos_5')
                param_dict['feature_names'].append('kinJntPos_6')
                param_dict['feature_names'].append('kinJntPos_7')

            if dataSample is None: dataSample = np.array(kinPos)
            else: dataSample = np.vstack([dataSample, kinPos])
            if 'kinPos_x' not in param_dict['feature_names']:
                param_dict['feature_names'].append('kinPos_x')
                param_dict['feature_names'].append('kinPos_y')
                param_dict['feature_names'].append('kinPos_z')

            if dataSample is None: dataSample = np.array(kinVel)
            else: dataSample = np.vstack([dataSample, kinVel])
            if 'kinVel_x' not in param_dict['feature_names']:
                param_dict['feature_names'].append('kinVel_x')
                param_dict['feature_names'].append('kinVel_y')
                param_dict['feature_names'].append('kinVel_z')
                

        ## # Unimodal feature - vision change ------------------------------------
        ## if 'unimodal_visionChange' in raw_feature_list:
        ##     visionChangeMag = d['visionChangeMagList'][idx]

        ##     unimodal_visionChange = visionChangeMag

        ##     if dataSample is None: dataSample = unimodal_visionChange
        ##     else: dataSample = np.vstack([dataSample, unimodal_visionChange])
        ##     if 'visionChange' not in param_dict['feature_names']:
        ##         param_dict['feature_names'].append('visionChange')
                
        ## # Unimodal feature - fabric skin ------------------------------------
        ## if 'unimodal_fabricForce' in raw_feature_list:
        ##     fabricMag = d['fabricMagList'][idx]

        ##     unimodal_fabricForce = fabricMag

        ##     if dataSample is None: dataSample = unimodal_fabricForce
        ##     else: dataSample = np.vstack([dataSample, unimodal_fabricForce])
        ##     if 'fabricForce' not in param_dict['feature_names']:
        ##         param_dict['feature_names'].append('fabricForce')


        # ----------------------------------------------------------------
        dataList.append(dataSample)


    # Augmentation -------------------------------------------------------
    # assuming there is no currupted file    
    assert len(dataList) == nSuccess+nFailure
    successDataList = dataList[0:nSuccess]
    failureDataList = dataList[nSuccess:]

    successDataAugList, failureDataAugList = data_augmentation(successDataList, failureDataList, \
                                                               nAugment=nAugment)
    allDataList = successDataAugList + failureDataAugList

    # Converting data structure & cutting unnecessary part ---------------
    features = np.swapaxes(allDataList, 0, 1)
    success_features = np.swapaxes(successDataList, 0, 1)
    failure_features = np.swapaxes(failureDataList, 0, 1)
    success_aug_features = np.swapaxes(successDataAugList, 0, 1)
    failure_aug_features = np.swapaxes(failureDataAugList, 0, 1)
               
    # Scaling ------------------------------------------------------------
    if isTrainingData:
        param_dict['feature_max'] = [ np.max(np.array(feature).flatten()) for feature in features ]
        param_dict['feature_min'] = [ np.min(np.array(feature).flatten()) for feature in features ]
        param_dict['feature_mu']  = [ np.mean(np.array(feature).flatten()) for feature in features ]
        param_dict['feature_std'] = [ np.std(np.array(feature).flatten()) for feature in features ]
        print "max: ", param_dict['feature_max']
        print "min: ", param_dict['feature_min']

    if False:
        success_features = normalization( success_features, param_dict['feature_mu'], param_dict['feature_std'] )
        failure_features = normalization( failure_features, param_dict['feature_mu'], param_dict['feature_std'] )
        success_aug_features = normalization( success_aug_features, param_dict['feature_mu'], \
                                              param_dict['feature_std'] )
        failure_aug_features = normalization( failure_aug_features, param_dict['feature_mu'], \
                                              param_dict['feature_std'] )
    else:
        success_features = scale( success_features, param_dict['feature_min'], param_dict['feature_max'] )
        failure_features = scale( failure_features, param_dict['feature_min'], param_dict['feature_max'] )
        success_aug_features = scale( success_aug_features, param_dict['feature_min'], \
                                              param_dict['feature_max'] )
        failure_aug_features = scale( failure_aug_features, param_dict['feature_min'], \
                                              param_dict['feature_max'] )


        
    param_dict['dataDim'] = dataDim
    
    ## scaled_features = []
    ## for i, feature in enumerate(features):

    ##     if abs( param_dict['feature_max'][i] - param_dict['feature_min'][i]) < 1e-3:
    ##         scaled_features.append( np.array(feature) )
    ##     else:
    ##         ## scaled_features.append( scale* ( np.array(feature) - param_dict['feature_min'][i] )\
    ##         ##                         /( param_dict['feature_max'][i] - param_dict['feature_min'][i]) )
    ##         scaled_features.append( ( np.array(feature) - param_dict['feature_mu'][i] )\
    ##                                 / param_dict['feature_std'][i] )
    
    return success_features, failure_features, success_aug_features, failure_aug_features, param_dict

#-------------------------------------------------------------------------------------------------

def normalization(x, mu, std):
    new_x = copy.copy(x)
    for i in xrange(len(x)):
        new_x[i] = (x[i]-mu[i])/std[i]
    return new_x

def scale(x, x_min, x_max):
    '''
    scale data between 0 and 1
    '''
    new_x = copy.copy(x)
    for i in xrange(len(x)):
        new_x[i] = (x[i]-x_min[i])/(x_max[i]-x_min[i])
    return new_x
    

## def changeDataStructure(dataList):
##     '''
##     From nSample x dim x length to dim x nSample x length
##     or
##     From dim x nSample x length to nSample x dim x length 
##     '''
    
##     n = len(dataList)
##     m = len(dataList[0])
##     features     = []
##     for i in xrange(m):
##         feature  = []

##         for j in xrange(n):
##             try:
##                 feature.append(dataList[j][i,:])
##             except:
##                 print "Failed to cut data", j,i, np.shape(dataList[j]), dataList[j][i]
##                 print np.shape(dataList), np.shape(dataList[j]), j, i
##                 sys.exit()

##         features.append( feature )

def data_augmentation(successes, failures, nAugment=1):

    '''
    nSamples x Dim x nLength
    '''
    c_scale  = [0.8, 1.2]
    c_shift  = [-10, 10]
    c_noise  = 20.0 # constant computing noise sgd, sample_std/constant
    c_filter = []

    nDim     = len(successes[0])
    np.random.seed(1342)

    if nAugment == 0: return successes, failures

    # for each sample
    for k in xrange(2):
        
        aug_data_list = []
        
        for x in [successes, failures][k]:
            
            # x is numpy 2D array
            for n in xrange(nAugment):

                # scaling (selective dim)
                ## idx_list = np.random.randint(0, 2, size=nDim)
                ## new_x = None
                ## for i, flag in zip( range(nDim), idx_list ):
                ##     if flag == 0: temp = x[i:i+1]
                ##     else: temp = x[i:i+1] * np.random.uniform(c_scale[0], c_scale[1])

                ##     if len(np.shape(temp)) == 1: temp = np.array([temp])

                ##     if new_x is None: new_x = temp
                ##     else: new_x = np.vstack([new_x, temp])

                ## aug_data_list.append(new_x)


                ## # shifting (selective dim)
                ## idx_list = np.random.randint(0, 2, size=nDim)
                ## new_x = None
                ## for i, flag in zip( range(nDim), idx_list ):
                ##     if flag == 0:
                ##         temp = x[i:i+1]
                ##     else:
                ##         shift = np.random.random_integers(c_shift[0], c_shift[1])
                ##         if shift >= 0:
                ##             temp = np.hstack([x[i][shift:], [x[i][-1]]*shift])
                ##         else:
                ##             temp = np.hstack([[x[i][0]]*abs(shift), x[i][:-abs(shift)]])

                ##     if len(np.shape(temp)) == 1: temp = np.array([temp])

                ##     if new_x is None: new_x = temp
                ##     else: new_x = np.vstack([new_x, temp])

                ## aug_data_list.append(new_x)

                # noise (all or selectively)
                idx_list = np.random.randint(0, 2, size=nDim)
                new_x = None
                for i, flag in zip( range(nDim), idx_list ):
                    if flag == 0: temp = x[i:i+1]
                    else: temp = x[i:i+1] + np.random.normal(0.0, np.std(x[i])/c_noise, len(x[i]))

                    if len(np.shape(temp)) == 1: temp = np.array([temp])

                    if new_x is None: new_x = temp
                    else: new_x = np.vstack([new_x, temp])

                aug_data_list.append(new_x)
                

                # filtering

        if k==0: success_aug_list = successes + aug_data_list
        else: failure_aug_list = failures + aug_data_list

    print "data auuuuuuuuuuuugmentation"
    print np.shape(success_aug_list), np.shape(failure_aug_list)
    
    return success_aug_list, failure_aug_list


def get_time_window_data(subject_names, task, raw_data_path, processed_data_path, save_pkl, \
                         rf_center, local_range, downSampleSize, time_window, feature_list, \
                         nAugment=1, renew=False):

    if os.path.isfile(save_pkl) and renew is not True:
        d = ut.load_pickle(save_pkl)
        # Time-sliding window
        new_normalTrainingData   = getTimeDelayData( d['normalTrainingData'], time_window )
        new_abnormalTrainingData = getTimeDelayData( d['abnormalTrainingData'], time_window )        
        new_normalTestData       = getTimeDelayData( d['normalTestData'], time_window )
        new_abnormalTestData     = getTimeDelayData( d['abnormalTestData'], time_window )        
        nSingleData              = len(d['normalTestData'][0][0])-time_window+1

        return new_normalTrainingData, new_normalTrainingData, new_normalTestData, new_abnormalTestData, \
          nSingleData

    # dim x sample x length
    successData, failureData, aug_successData, aug_failureData, param_dict = \
      getDataSet(subject_names, task, raw_data_path, \
                 processed_data_path, rf_center, local_range,\
                 downSampleSize=downSampleSize, \
                 scale=1.0,\
                 ae_data=True, data_ext=False, nAugment=nAugment, \
                 feature_list=feature_list, \
                 data_renew=renew)

    # index selection
    ratio        = 0.8
    success_idx  = range(len(aug_successData[0]))
    failure_idx  = range(len(aug_failureData[0]))

    s_train_idx  = random.sample(success_idx, int( ratio*len(success_idx)) )
    f_train_idx  = random.sample(failure_idx, int( ratio*len(failure_idx)) )
    
    s_test_idx = [x for x in success_idx if not x in s_train_idx]
    f_test_idx = [x for x in failure_idx if not x in f_train_idx]

    # data structure: dim x sample x sequence
    normalTrainingData   = aug_successData[:, s_train_idx, :]
    abnormalTrainingData = aug_failureData[:, f_train_idx, :]
    normalTestData       = aug_successData[:, s_test_idx, :]
    abnormalTestData     = aug_failureData[:, f_test_idx, :]

    # scaling by the number of dimensions in each feature
    # nSamples x Dim x nLength
    d = {}        
    d['normalTrainingData']   = np.swapaxes(normalTrainingData, 0, 1)
    d['abnormalTrainingData'] = np.swapaxes(abnormalTrainingData, 0, 1)
    d['normalTestData']       = np.swapaxes(normalTestData, 0, 1)
    d['abnormalTestData']     = np.swapaxes(abnormalTestData, 0, 1)
    ut.save_pickle(d, save_pkl)

    print "======================================"
    print "nSamples x Dim x nLength"
    print "--------------------------------------"
    print "Normal Train data: ",   np.shape(d['normalTrainingData'])
    print "Abnormal Train data: ", np.shape(d['abnormalTrainingData'])
    print "Normal test data: ",    np.shape(d['normalTestData'])
    print "Abnormal test data: ",  np.shape(d['abnormalTestData'])
    print "======================================"

    # Time-sliding window
    # sample x time_window_flatten_length
    new_normalTrainingData   = getTimeDelayData( d['normalTrainingData'], time_window )
    new_abnormalTrainingData = getTimeDelayData( d['abnormalTrainingData'], time_window )
    new_normalTestData       = getTimeDelayData( d['normalTestData'], time_window )
    new_abnormalTestData     = getTimeDelayData( d['abnormalTestData'], time_window )
    nSingleData       = len(d['normalTestData'][0][0])-time_window+1

    # sample x dim
    return new_normalTrainingData, new_abnormalTrainingData, \
      new_normalTestData, new_abnormalTestData, nSingleData


def getTimeDelayData(data, time_window):
    '''
    Input size is sample x dim x length.
    Output size is sample x time_window_flatten_length.
    '''

    new_data = []
    for i in xrange(len(data)):
        for j in xrange(len(data[i][0])-time_window+1):
            new_data.append( data[i][:,j:j+time_window].flatten() )

    return np.array(new_data)
