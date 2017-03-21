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
import numpy as np
import scipy
import hrl_lib.util as ut
from joblib import Parallel, delayed

# Private utils
from hrl_anomaly_detection.util import *
from hrl_anomaly_detection.util_viz import *
from hrl_anomaly_detection import data_manager as dm
from hrl_anomaly_detection import util as util
from hrl_execution_monitor import util as autil

# Private learners
from hrl_anomaly_detection.hmm import learning_hmm as hmm
import hrl_anomaly_detection.classifiers.classifier as cf
import hrl_anomaly_detection.data_viz as dv

# visualization
import matplotlib
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from matplotlib import gridspec
import itertools
colors = itertools.cycle(['g', 'm', 'c', 'k', 'y','r', 'b', ])
shapes = itertools.cycle(['x','v', 'o', '+'])

matplotlib.rcParams['pdf.fonttype'] = 42
matplotlib.rcParams['ps.fonttype'] = 42 
random.seed(3334)
np.random.seed(3334)





def gen_likelihoods(subject_names, task_name, raw_data_path, processed_data_path, param_dict,\
                    data_renew=False, save_pdf=False, verbose=False):
    ## Parameters
    # data
    data_dict  = param_dict['data_param']
    data_renew = data_dict['renew']
    # HMM
    HMM_dict   = param_dict['HMM']
    nState     = HMM_dict['nState']
    cov        = HMM_dict['cov']

    # parameters
    startIdx    = 4
    
    #------------------------------------------
   
    if os.path.isdir(processed_data_path) is False:
        os.system('mkdir -p '+processed_data_path)

    crossVal_pkl = os.path.join(processed_data_path, 'cv_'+task_name+'.pkl')
    
    if os.path.isfile(crossVal_pkl) and data_renew is False:
        print "CV data exists and no renew"
        d = ut.load_pickle(crossVal_pkl)
        kFold_list = d['kFoldList'] 
        successData = d['successData']
        failureData = d['failureData']
        success_files = d['success_files']
        failure_files = d['failure_files']        
    else:
        '''
        Use augmented data? if nAugment is 0, then aug_successData = successData
        '''        
        d = dm.getDataLOPO(subject_names, task_name, raw_data_path, \
                           processed_data_path, data_dict['rf_center'], data_dict['local_range'],\
                           downSampleSize=data_dict['downSampleSize'],\
                           handFeatures=data_dict['isolationFeatures'], \
                           cut_data=data_dict['cut_data'], \
                           data_renew=data_renew, max_time=data_dict['max_time'])


        successData, failureData, success_files, failure_files, kFold_list \
          = dm.LOPO_data_index(d['successDataList'], d['failureDataList'],\
                               d['successFileList'], d['failureFileList'],\
                               target_class=target_class)

        d['successData']   = successData
        d['failureData']   = failureData
        d['success_files']   = success_files
        d['failure_files']   = failure_files        
        d['kFoldList']     = kFold_list
        ut.save_pickle(d, crossVal_pkl)


    # select feature for detection
    feature_list = []
    for feature in param_dict['data_param']['handFeatures']:
        idx = [ i for i, x in enumerate(param_dict['data_param']['isolationFeatures']) if feature == x][0]
        feature_list.append(idx)
    
    successData = successData[feature_list]
    failureData = failureData[feature_list]

    kFold_list = kFold_list[:1]

    #-----------------------------------------------------------------------------------------    
    # Training HMM, and getting classifier training and testing data
    noise_mag = [0.03,0.1,0.03,0.08] #0.01
    dm.saveHMMinducedFeatures(kFold_list, successData, failureData,\
                              task_name, processed_data_path,\
                              HMM_dict, data_renew, startIdx, nState, cov, \
                              success_files=success_files, failure_files=failure_files,\
                              noise_mag=noise_mag, diag=False, cov_type='full', \
                              inc_hmm_param=True, verbose=verbose)
    print "------------------------------------------------------------"
    
    # HMM-induced vector with LOPO
    for idx, (normalTrainIdx, abnormalTrainIdx, normalTestIdx, abnormalTestIdx) \
      in enumerate(kFold_list):
      break

    model_pkl = os.path.join(processed_data_path, 'hmm_'+task_name+'_'+str(idx)+'.pkl')
    d         = ut.load_pickle(model_pkl)
    normalTrainData = copy.copy(successData[:, normalTrainIdx, :]) * HMM_dict['scale']
    normalTestData  = copy.copy(successData[:, normalTestIdx, :]) * HMM_dict['scale'] 
    ll_train_logps  = d['ll_classifier_train_X'] 
    ll_test_logps  = d['ll_classifier_test_X']
    

    # Get ml object
    nEmissionDim = len(successData)
    ml = hmm.learning_hmm(nState, nEmissionDim, verbose=verbose)
    ml.set_hmm_object(d['A'], d['B'], d['pi'], d['out_a_num'], d['vec_num'], \
                      d['mat_num'], d['u_denom'])

    # generate samples
    m = 10
    nLength = 140
    seqs = ml.generate_sample(m, 140)

    # compute likelihoods
    ll_logps = ml.loglikelihoods_from_seqs(seqs, startIdx=4)    

    # display
    fig = plt.figure()
    for i in xrange(nEmissionDim):
        fig.add_subplot((nEmissionDim+1)*100+10+1+i)
        
        for j in xrange(len(seqs)):
            x = np.array(seqs[j]).reshape((nLength,nEmissionDim)).T            
            plt.plot( x[i], 'r-' )

        for j in xrange(len(normalTrainData[i])):
            plt.plot( normalTrainData[i][j], 'b-', alpha=0.4 )

        
    fig.add_subplot((nEmissionDim+1)*100+10+nEmissionDim+1)
    plt.plot(np.array(ll_logps)[:,startIdx:].T, 'r-')
    for j in xrange(len(ll_train_logps)):
        plt.plot( np.array(ll_train_logps[j])[:,0].T, 'b-', alpha=0.4 )
    for j in xrange(len(ll_test_logps)):        
        plt.plot( np.array(ll_test_logps[j])[:,0].T, 'g-', alpha=0.4 )

    plt.show()








def evaluation_single_ad(subject_names, task_name, raw_data_path, processed_data_path, param_dict,\
                         data_renew=False, save_pdf=False, verbose=False, debug=False,\
                         no_plot=False, delay_plot=True, find_param=False, data_gen=False,\
                         target_class=None):
    ## Parameters
    # data
    data_dict  = param_dict['data_param']
    data_renew = data_dict['renew']
    # HMM
    HMM_dict   = param_dict['HMM']
    nState     = HMM_dict['nState']
    cov        = HMM_dict['cov']
    # SVM
    SVM_dict   = param_dict['SVM']

    # ROC
    ROC_dict = param_dict['ROC']

    # parameters
    startIdx    = 4
    method_list = ROC_dict['methods'] 
    nPoints     = ROC_dict['nPoints']
    
    #------------------------------------------

    if os.path.isdir(processed_data_path) is False:
        os.system('mkdir -p '+processed_data_path)

    crossVal_pkl = os.path.join(processed_data_path, 'cv_'+task_name+'.pkl')
    
    if os.path.isfile(crossVal_pkl) and data_renew is False and data_gen is False:
        print "CV data exists and no renew"
        d = ut.load_pickle(crossVal_pkl)
        kFold_list = d['kFoldList'] 
        successData = d['successData']
        failureData = d['failureData']
        success_files = d['success_files']
        failure_files = d['failure_files']        
    else:
        '''
        Use augmented data? if nAugment is 0, then aug_successData = successData
        '''        
        d = dm.getDataLOPO(subject_names, task_name, raw_data_path, \
                           processed_data_path, data_dict['rf_center'], data_dict['local_range'],\
                           downSampleSize=data_dict['downSampleSize'],\
                           handFeatures=data_dict['isolationFeatures'], \
                           cut_data=data_dict['cut_data'], \
                           data_renew=data_renew, max_time=data_dict['max_time'])


        successData, failureData, success_files, failure_files, kFold_list \
          = dm.LOPO_data_index(d['successDataList'], d['failureDataList'],\
                               d['successFileList'], d['failureFileList'],\
                               target_class=target_class)

        d['successData']   = successData
        d['failureData']   = failureData
        d['success_files']   = success_files
        d['failure_files']   = failure_files        
        d['kFoldList']     = kFold_list
        ut.save_pickle(d, crossVal_pkl)
        if data_gen: sys.exit()


    # select feature for detection
    feature_list = []
    for feature in param_dict['data_param']['handFeatures']:
        idx = [ i for i, x in enumerate(param_dict['data_param']['isolationFeatures']) if feature == x][0]
        feature_list.append(idx)

    successData = successData[feature_list]
    failureData = failureData[feature_list]

    # temp
    ## kFold_list = kFold_list[:8]

    #-----------------------------------------------------------------------------------------    
    # Training HMM, and getting classifier training and testing data
    noise_mag = 0.03
    dm.saveHMMinducedFeatures(kFold_list, successData, failureData,\
                              task_name, processed_data_path,\
                              HMM_dict, data_renew, startIdx, nState, cov, \
                              success_files=success_files, failure_files=failure_files,\
                              noise_mag=noise_mag, diag=False, cov_type='full', \
                              inc_hmm_param=True, verbose=verbose)
    print "------------------------------------------------------------"

    d['param_dict']['feature_names'] = np.array(d['param_dict']['feature_names'])[feature_list].tolist()
    d['param_dict']['feature_min'] = np.array(d['param_dict']['feature_min'])[feature_list].tolist()
    d['param_dict']['feature_max'] = np.array(d['param_dict']['feature_max'])[feature_list].tolist()

    tgt_raw_data_path  = os.path.expanduser('~')+'/hrl_file_server/dpark_data/anomaly/RAW_DATA/ICRA2017/'
    tgt_subjects = ['zack', 'hkim', 'ari', 'park', 'jina', 'linda']

    # Extract data from designated location
    td = dm.getDataLOPO(tgt_subjects, task_name, tgt_raw_data_path, save_data_path,\
                        downSampleSize=data_dict['downSampleSize'],\
                        init_param_dict=d['param_dict'],\
                        handFeatures=param_dict['data_param']['handFeatures'], \
                        data_renew=True, max_time=data_dict['max_time'],
                        pkl_prefix='tgt_')

    nEmissionDim = len(param_dict['data_param']['handFeatures'])

    ## # Comparison of
    ## from hrl_anomaly_detection import data_viz as dv
    ## import hmm_viz as hv
    
    ## hv.data_viz(successData, td['successDataList'][0], raw_viz=True)
    ## hv.data_viz(successData, td['successDataList'][0], raw_viz=True,
    ##             minmax=(d['param_dict']['feature_min'], d['param_dict']['feature_max'] ))
    ## dv.viz( successData, minmax=(d['param_dict']['feature_min'], d['param_dict']['feature_max'] ) )
    ## dv.viz( td['successDataList'][0], minmax=(d['param_dict']['feature_min'], d['param_dict']['feature_max'] ) )

    # person-wise indices from normal training data
    nor_train_inds = [ np.arange(len(kFold_list[i][2])) for i in xrange(len(kFold_list)) ]
    for i in xrange(1,len(nor_train_inds)):
        nor_train_inds[i] += (nor_train_inds[i-1][-1]+1)
    normalTrainData  = copy.copy(successData) * HMM_dict['scale']
    
    # Split test data to two groups
    n_AHMM_sample = 10
    for idx in xrange(len(td['successDataList'])):

        ## if idx != 4: continue
        inc_model_pkl = os.path.join(processed_data_path, 'hmm_update_'+task_name+'_'+str(idx)+'.pkl')
        if not(os.path.isfile(inc_model_pkl) is False or HMM_dict['renew'] or data_renew) and False:
            print idx, " : updated hmm exists"
            continue

        normalTestData   = np.array(copy.copy(td['successDataList'][idx])) * HMM_dict['scale'] 
        abnormalTestData = np.array(copy.copy(td['failureDataList'][idx])) * HMM_dict['scale']

        ## noise_mag=0.01
        X_ptrain = copy.copy(normalTestData[:n_AHMM_sample])
        noise_arr = np.random.normal(0.0, noise_mag, np.shape(X_ptrain))*HMM_dict['scale']
        nLength   = len(normalTestData[0][0]) - startIdx
      
        model_pkl = os.path.join(processed_data_path, 'hmm_'+task_name+'_'+str(0)+'.pkl')
        d         = ut.load_pickle(model_pkl)

        # Update
        ml = hmm.learning_hmm(nState, d['nEmissionDim'])
        ml.set_hmm_object(d['A'], d['B'], d['pi'], d['out_a_num'], d['vec_num'], \
                          d['mat_num'], d['u_denom'])
        ret = ml.partial_fit(X_ptrain+noise_arr, learningRate=0.005 )
        ## ret = ml.fit(X_ptrain+noise_arr)
        ## print idx, ret
        if np.isnan(ret):
            print "kFold_list ........ partial fit error... "
            print ret
            sys.exit()

        # Comparison of
        ## import hmm_viz as hv
        ## hv.data_viz(normalTrainData, X_ptrain)
        ## sys.exit()

        # Comparison of HMMs
        ## ml_temp = hmm.learning_hmm(nState, d['nEmissionDim'])
        ## ml_temp.set_hmm_object(d['A'], d['B'], d['pi'], d['out_a_num'], d['vec_num'], \
        ##                        d['mat_num'], d['u_denom'])
        ## import hmm_viz as hv
        ## hv.hmm_emission_viz(ml_temp, ml)
        ## sys.exit()

        # Classifier test data
        n_jobs=-1
        ll_classifier_train_X, ll_classifier_train_Y, ll_classifier_train_idx =\
          hmm.getHMMinducedFeaturesFromRawFeatures(ml, normalTrainData, startIdx=startIdx, n_jobs=n_jobs)
        ll_classifier_ptrain_X, ll_classifier_ptrain_Y, ll_classifier_ptrain_idx =\
          hmm.getHMMinducedFeaturesFromRawFeatures(ml, normalTestData[:,:n_AHMM_sample], startIdx=startIdx, \
                                                   n_jobs=n_jobs)
        ll_classifier_test_X, ll_classifier_test_Y, ll_classifier_test_idx =\
          hmm.getHMMinducedFeaturesFromRawFeatures(ml, normalTestData[:,n_AHMM_sample:], abnormalTestData, \
                                                   startIdx, n_jobs=n_jobs)

        ## if success_files is not None:
        ##     ll_classifier_test_labels = [success_files[i] for i in normalTestIdx[n_AHMM_sample:]]
        ##     ll_classifier_test_labels += [failure_files[i] for i in abnormalTestIdx]
        ## else:
        ll_classifier_test_labels = None

        #-----------------------------------------------------------------------------------------
        d = {}
        d['nEmissionDim'] = ml.nEmissionDim
        d['A']            = ml.A 
        d['B']            = ml.B 
        d['pi']           = ml.pi
        d['F']            = ml.F
        d['nState']       = nState
        d['startIdx']     = startIdx
        d['ll_classifier_train_X']  = ll_classifier_train_X
        d['ll_classifier_train_Y']  = ll_classifier_train_Y            
        d['ll_classifier_train_idx']= ll_classifier_train_idx
        ## d['ll_classifier_train_X']  = ll_classifier_ptrain_X
        ## d['ll_classifier_train_Y']  = ll_classifier_ptrain_Y            
        ## d['ll_classifier_train_idx']= ll_classifier_ptrain_idx
        d['ll_classifier_ptrain_X']  = ll_classifier_ptrain_X
        d['ll_classifier_ptrain_Y']  = ll_classifier_ptrain_Y            
        d['ll_classifier_ptrain_idx']= ll_classifier_ptrain_idx
        d['ll_classifier_test_X']   = ll_classifier_test_X
        d['ll_classifier_test_Y']   = ll_classifier_test_Y            
        d['ll_classifier_test_idx'] = ll_classifier_test_idx
        d['ll_classifier_test_labels'] = ll_classifier_test_labels
        d['nLength']      = nLength
        d['scale']        = HMM_dict['scale']
        d['cov']          = HMM_dict['cov']
        d['nor_train_inds'] = nor_train_inds
        ut.save_pickle(d, inc_model_pkl)
      
    pkl_prefix = 'hmm_update_'+task_name


    #-----------------------------------------------------------------------------------------
    roc_pkl = os.path.join(processed_data_path, 'roc_update_'+task_name+'.pkl')

    if os.path.isfile(roc_pkl) is False or HMM_dict['renew'] or SVM_dict['renew']: ROC_data = {}
    else: ROC_data = ut.load_pickle(roc_pkl)
    ROC_data = util.reset_roc_data(ROC_data, method_list, ROC_dict['update_list'], nPoints)

    # parallelization
    if debug: n_jobs=1
    else: n_jobs=-1
    l_data = Parallel(n_jobs=n_jobs, verbose=10)(delayed(cf.run_classifiers)( idx, processed_data_path, \
                                                                         task_name, \
                                                                         method_list[0], ROC_data, \
                                                                         ROC_dict, \
                                                                         SVM_dict, HMM_dict, \
                                                                         startIdx=startIdx, nState=nState,\
                                                                         n_jobs=n_jobs,\
                                                                         modeling_pkl_prefix=pkl_prefix,\
                                                                         adaptation=True) \
                                                                         for idx in xrange(len(td['successDataList'])) )

    print "finished to run run_classifiers"
    ROC_data = util.update_roc_data(ROC_data, l_data, nPoints, method_list)
    ut.save_pickle(ROC_data, roc_pkl)

    # ---------------- ROC Visualization ----------------------
    roc_info(ROC_data, nPoints, no_plot=no_plot, ROC_dict=ROC_dict)
    ## class_info(method_list, ROC_data, nPoints, kFold_list)



## def temp():

##     # Split test data to two groups
##     n_AHMM_sample = 10
##     for idx, (normalTrainIdx, abnormalTrainIdx, normalTestIdx, abnormalTestIdx) \
##       in enumerate(kFold_list):

##         ## if idx != 4: continue
##         inc_model_pkl = os.path.join(processed_data_path, 'hmm_update_'+task_name+'_'+str(idx)+'.pkl')
##         if not(os.path.isfile(inc_model_pkl) is False or HMM_dict['renew'] or data_renew) and False :
##             print idx, " : updated hmm exists"
##             continue
 
##         normalTrainData  = copy.copy(successData[:, normalTrainIdx, :]) * HMM_dict['scale']
##         normalTestData   = copy.copy(successData[:, normalTestIdx, :]) * HMM_dict['scale'] 
##         abnormalTestData = copy.copy(failureData[:, abnormalTestIdx, :]) * HMM_dict['scale']

##         # person-wise indices from normal training data
##         nor_train_inds = [ np.arange(len(kFold_list[i][2])) for i in xrange(len(kFold_list)) if i!=idx ]
##         for i in xrange(1,len(nor_train_inds)):
##             nor_train_inds[i] += (nor_train_inds[i-1][-1]+1)

##         ## noise_mag=0.01
##         X_ptrain = copy.copy(normalTestData[:n_AHMM_sample])
##         noise_arr = np.random.normal(0.0, noise_mag, np.shape(X_ptrain))*HMM_dict['scale']
##         nLength   = len(normalTestData[0][0]) - startIdx
      
##         model_pkl = os.path.join(processed_data_path, 'hmm_'+task_name+'_'+str(idx)+'.pkl')
##         d            = ut.load_pickle(model_pkl)

##         # Update
##         ml = hmm.learning_hmm(nState, d['nEmissionDim'])
##         ## ml.set_hmm_object(d['A'], d['B'], d['pi'], d['out_a_num'], d['vec_num'], \
##         ##                   d['mat_num'], d['u_denom'])
##         ## ret = ml.partial_fit(X_ptrain+noise_arr, learningRate=0.9)
##         ret = ml.fit(X_ptrain+noise_arr)
##         print idx, ret
##         if np.isnan(ret):
##             print "kFold_list ........ partial fit error... "
##             print ret
##             sys.exit()

##         # Comparison of
##         ## import hmm_viz as hv
##         ## ## hv.data_viz(normalTrainData[:,40:60], X_ptrain)
##         ## hv.data_viz(normalTrainData, X_ptrain)
##         ## sys.exit()

##         # Comparison of HMMs
##         ml_temp = hmm.learning_hmm(nState, d['nEmissionDim'])
##         ml_temp.set_hmm_object(d['A'], d['B'], d['pi'], d['out_a_num'], d['vec_num'], \
##                                d['mat_num'], d['u_denom'])
##         import hmm_viz as hv
##         hv.hmm_emission_viz(ml_temp, ml)
##         sys.exit()

##         # Classifier test data
##         n_jobs=-1
##         ll_classifier_train_X, ll_classifier_train_Y, ll_classifier_train_idx =\
##           hmm.getHMMinducedFeaturesFromRawFeatures(ml, normalTrainData, startIdx=startIdx, n_jobs=n_jobs)
##         ll_classifier_ptrain_X, ll_classifier_ptrain_Y, ll_classifier_ptrain_idx =\
##           hmm.getHMMinducedFeaturesFromRawFeatures(ml, normalTestData[:,:n_AHMM_sample], startIdx=startIdx, \
##                                                    n_jobs=n_jobs)
##         ll_classifier_test_X, ll_classifier_test_Y, ll_classifier_test_idx =\
##           hmm.getHMMinducedFeaturesFromRawFeatures(ml, normalTestData[:,n_AHMM_sample:], abnormalTestData, \
##                                                    startIdx, n_jobs=n_jobs)

##         if success_files is not None:
##             ll_classifier_test_labels = [success_files[i] for i in normalTestIdx[n_AHMM_sample:]]
##             ll_classifier_test_labels += [failure_files[i] for i in abnormalTestIdx]
##         else:
##             ll_classifier_test_labels = None

##         #-----------------------------------------------------------------------------------------
##         d = {}
##         d['nEmissionDim'] = ml.nEmissionDim
##         d['A']            = ml.A 
##         d['B']            = ml.B 
##         d['pi']           = ml.pi
##         d['F']            = ml.F
##         d['nState']       = nState
##         d['startIdx']     = startIdx
##         d['ll_classifier_train_X']  = ll_classifier_train_X
##         d['ll_classifier_train_Y']  = ll_classifier_train_Y            
##         d['ll_classifier_train_idx']= ll_classifier_train_idx
##         d['ll_classifier_ptrain_X']  = ll_classifier_ptrain_X
##         d['ll_classifier_ptrain_Y']  = ll_classifier_ptrain_Y            
##         d['ll_classifier_ptrain_idx']= ll_classifier_ptrain_idx
##         d['ll_classifier_test_X']   = ll_classifier_test_X
##         d['ll_classifier_test_Y']   = ll_classifier_test_Y            
##         d['ll_classifier_test_idx'] = ll_classifier_test_idx
##         d['ll_classifier_test_labels'] = ll_classifier_test_labels
##         d['nLength']      = nLength
##         d['scale']        = HMM_dict['scale']
##         d['cov']          = HMM_dict['cov']
##         d['nor_train_inds'] = nor_train_inds
##         ut.save_pickle(d, inc_model_pkl)
    



def evaluation_double_ad(subject_names, task_name, raw_data_path, processed_data_path, param_dict,\
                         data_renew=False, save_pdf=False, verbose=False, debug=False,\
                         no_plot=False, delay_plot=True, find_param=False, data_gen=False):

    ## Parameters
    # data
    data_dict  = param_dict['data_param']
    data_renew = data_dict['renew']
    # HMM
    HMM_dict   = param_dict['HMM']
    nState     = HMM_dict['nState']
    cov        = HMM_dict['cov']
    # SVM
    SVM_dict   = param_dict['SVM']
    # ROC
    ROC_dict = param_dict['ROC']

    # parameters
    startIdx    = 4
    method_list = ROC_dict['methods'] 
    nPoints     = ROC_dict['nPoints']
    
    #------------------------------------------
    if os.path.isdir(processed_data_path) is False:
        os.system('mkdir -p '+processed_data_path)

    crossVal_pkl = os.path.join(processed_data_path, 'cv_'+task_name+'.pkl')
    
    if os.path.isfile(crossVal_pkl) and data_renew is False and data_gen is False:
        print "CV data exists and no renew"
        d = ut.load_pickle(crossVal_pkl)
        kFold_list    = d['kFoldList'] 
        successData   = d['successData']
        failureData   = d['failureData']        
        success_files = d['success_files']
        failure_files = d['failure_files']
    else:
        '''
        Use augmented data? if nAugment is 0, then aug_successData = successData
        '''        
        d = dm.getDataLOPO(subject_names, task_name, raw_data_path, \
                           processed_data_path, data_dict['rf_center'], data_dict['local_range'],\
                           downSampleSize=data_dict['downSampleSize'],\
                           handFeatures=data_dict['isolationFeatures'], \
                           cut_data=data_dict['cut_data'], \
                           data_renew=data_renew, max_time=data_dict['max_time'],
                           ros_bag_image=True)
                           
        successData, failureData, success_files, failure_files, kFold_list \
          = dm.LOPO_data_index(d['successDataList'], d['failureDataList'],\
                               d['successFileList'], d['failureFileList'])

        d['successData']   = successData
        d['failureData']   = failureData
        d['success_files'] = success_files
        d['failure_files'] = failure_files
        d['kFoldList']     = kFold_list
        ut.save_pickle(d, crossVal_pkl)
        if data_gen: sys.exit()

    #-----------------------------------------------------------------------------------------
    # feature selection
    print d['param_dict']['feature_names']    
    feature_idx_list = []
    for i in xrange(2):

        feature_idx_list.append([])
        for feature in param_dict['data_param']['handFeatures'][i]:
            feature_idx_list[i].append(data_dict['isolationFeatures'].index(feature))

        success_data_ad = copy.copy(successData[feature_idx_list[i]])
        failure_data_ad = copy.copy(failureData[feature_idx_list[i]])
        HMM_dict_local = copy.deepcopy(HMM_dict)
        HMM_dict_local['scale'] = param_dict['HMM']['scale'][i]

        ## #temp
        ## if i==0: continue

        # Training HMM, and getting classifier training and testing data
        dm.saveHMMinducedFeatures(kFold_list, success_data_ad, failure_data_ad,\
                                  task_name, processed_data_path,\
                                  HMM_dict_local, data_renew, startIdx, nState, cov, \
                                  success_files=success_files, failure_files=failure_files,\
                                  noise_mag=0.03, diag=False, suffix=str(i),\
                                  verbose=verbose)

    print "Finished to save hmm data"

    #-----------------------------------------------------------------------------------------
    roc_pkl = os.path.join(processed_data_path, 'roc_'+task_name+'.pkl')

    if os.path.isfile(roc_pkl) is False or HMM_dict['renew'] or SVM_dict['renew']: ROC_data = {}
    else: ROC_data = ut.load_pickle(roc_pkl)
    ROC_data = util.reset_roc_data(ROC_data, [method_list[0][:-1]], ROC_dict['update_list'], nPoints)

    # temp
    kFold_list = kFold_list[:8]

    # parallelization
    if debug: n_jobs=1
    else: n_jobs=-1
    l_data = Parallel(n_jobs=n_jobs, verbose=10)\
      (delayed(cf.run_classifiers_boost)( idx, processed_data_path, \
                                          task_name, \
                                          method_list, ROC_data, \
                                          param_dict,\
                                          startIdx=startIdx, nState=nState) \
      for idx in xrange(len(kFold_list)) )

    print "finished to run run_classifiers"
    ROC_data = util.update_roc_data(ROC_data, l_data, nPoints, [method_list[0][:-1]])
    ut.save_pickle(ROC_data, roc_pkl)

    
    # ---------------- ROC Visualization ----------------------
    roc_info(ROC_data, nPoints, no_plot=True, multi_ad=True, ROC_dict=ROC_dict)
    ## class_info(method_list, ROC_data, nPoints, kFold_list)





if __name__ == '__main__':

    import optparse
    p = optparse.OptionParser()
    util.initialiseOptParser(p)

    p.add_option('--gen_likelihood', '--gl', action='store_true', dest='gen_likelihoods',
                 default=False, help='Generate likelihoods.')
    p.add_option('--eval_single', '--es', action='store_true', dest='evaluation_single',
                 default=False, help='Evaluate with single detector.')
    p.add_option('--eval_double', '--ed', action='store_true', dest='evaluation_double',
                 default=False, help='Evaluate with double detectors.')
    
    opt, args = p.parse_args()

    #---------------------------------------------------------------------------           
    # Run evaluation
    #---------------------------------------------------------------------------           
    rf_center     = 'kinEEPos'        
    scale         = 1.0
    local_range   = 10.0
    nPoints = 40 #None

    from hrl_anomaly_detection.adaptation.TCDS2017_params import *
    raw_data_path, save_data_path, param_dict = getParams(opt.task, opt.bDataRenew, \
                                                          opt.bHMMRenew, opt.bCLFRenew, opt.dim,\
                                                          rf_center, local_range, nPoints=nPoints)
    if opt.bNoUpdate: param_dict['ROC']['update_list'] = []
    # Mikako - bad camera
    # s1 - kaci - before camera calibration
    subjects = ['s2', 's3','s4','s5', 's6','s7','s8', 's9']

    save_data_path = os.path.expanduser('~')+\
      '/hrl_file_server/dpark_data/anomaly/TCDS2017/'+opt.task+'_data_adaptation/'+\
      str(param_dict['data_param']['downSampleSize'])+'_'+str(opt.dim)
    ## target_class = [11,4,13,10]


    ## # aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
    ## raw_data_path  = os.path.expanduser('~')+'/hrl_file_server/dpark_data/anomaly/RAW_DATA/ICRA2017/'    
    ## save_data_path = os.path.expanduser('~')+\
    ##   '/hrl_file_server/dpark_data/anomaly/TCDS2017/'+opt.task+'_data_adaptation2/'+\
    ##   str(param_dict['data_param']['downSampleSize'])+'_'+str(opt.dim)
    ## subjects = ['zack']
    ## param_dict['data_param']['downSampleSize'] = 200


    #---------------------------------------------------------------------------           
    if opt.bRawDataPlot or opt.bInterpDataPlot:
        '''
        Before localization: Raw data plot
        After localization: Raw or interpolated data plot
        '''
        successData = True
        failureData = False
        modality_list   = ['kinematics', 'kinematics_des', 'audioWrist', 'ft', 'vision_landmark'] # raw plot

        dv.data_plot(subjects, opt.task, raw_data_path, save_data_path,\
                  downSampleSize=param_dict['data_param']['downSampleSize'], \
                  local_range=local_range, rf_center=rf_center, global_data=True, \
                  raw_viz=opt.bRawDataPlot, interp_viz=opt.bInterpDataPlot, save_pdf=opt.bSavePdf,\
                  successData=successData, failureData=failureData,\
                  continuousPlot=True, \
                  modality_list=modality_list, data_renew=opt.bDataRenew, verbose=opt.bVerbose)

    elif opt.bFeaturePlot:
        success_viz = True
        failure_viz = False
        param_dict['data_param']['handFeatures'] = ['unimodal_audioWristRMS', \
                                                    ## 'unimodal_audioWristFrontRMS', \
                                                    ## 'unimodal_audioWristAzimuth',\
                                                    'unimodal_kinVel',\
                                                    'unimodal_kinJntEff_1', \
                                                    ## 'unimodal_kinJntEff', \
                                                    'unimodal_ftForce_integ', \
                                                    ## 'unimodal_ftForce_delta', \
                                                    'unimodal_ftForce_zero', \
                                                    ## 'unimodal_ftForce', \
                                                    ## 'unimodal_ftForceX', \
                                                    ## 'unimodal_ftForceY', \
                                                    ## 'unimodal_ftForceZ', \
                                                    ## 'unimodal_kinEEChange', \
                                                    'unimodal_kinDesEEChange', \
                                                    'crossmodal_landmarkEEDist', \
                                                    ## 'crossmodal_landmarkEEAng',\
                                                    ## 'unimodal_fabricForce',\
                                                    ## 'unimodal_landmarkDist'
                                                    ]
        ## target_class = [13]
        ## param_dict['data_param']['handFeatures'] = ['unimodal_kinJntEff_1']
        
        dm.getDataLOPO(subjects, opt.task, raw_data_path, save_data_path,
                       param_dict['data_param']['rf_center'], param_dict['data_param']['local_range'],\
                       downSampleSize=param_dict['data_param']['downSampleSize'], \
                       success_viz=success_viz, failure_viz=failure_viz,\
                       cut_data=param_dict['data_param']['cut_data'],\
                       save_pdf=opt.bSavePdf, solid_color=True,\
                       handFeatures=param_dict['data_param']['handFeatures'], data_renew=opt.bDataRenew, \
                       max_time=param_dict['data_param']['max_time']) #, target_class=target_class)

    elif opt.bLikelihoodPlot:
        param_dict['HMM']['scale'] = 5.0
        param_dict['data_param']['handFeatures'] = ['unimodal_audioWristRMS',  \
                                                    'unimodal_kinJntEff_1',\
                                                    'unimodal_ftForce_integ',\
                                                    'unimodal_kinEEChange', \
                                                    'crossmodal_landmarkEEDist', \
                                                    ]
        param_dict['ROC']['hmmgp_param_range'] = np.logspace(-0.6, 2.3, nPoints)*-1.0

        import hrl_anomaly_detection.data_viz as dv        
        dv.vizLikelihoods(subjects, opt.task, raw_data_path, save_data_path, param_dict,\
                          decision_boundary_viz=False, method='progress', \
                          useTrain=True, useNormalTest=False, useAbnormalTest=True,\
                          useTrain_color=False, useNormalTest_color=False, useAbnormalTest_color=False,\
                          hmm_renew=opt.bHMMRenew, data_renew=opt.bDataRenew, save_pdf=opt.bSavePdf,\
                          verbose=opt.bVerbose, lopo=True, plot_feature=False)


    elif opt.gen_likelihoods:
        ## ep 12-89.5 7-82
        save_data_path = os.path.expanduser('~')+\
          '/hrl_file_server/dpark_data/anomaly/TCDS2017/'+opt.task+'_data_adaptation/'+\
          str(param_dict['data_param']['downSampleSize'])+'_'+str(opt.dim)
        param_dict['data_param']['handFeatures'] = ['unimodal_audioWristRMS',  \
                                                     'unimodal_kinJntEff_1',\
                                                     'unimodal_ftForce_integ',\
                                                     'crossmodal_landmarkEEDist']
        param_dict['HMM']['scale'] = 5.0
        
        gen_likelihoods(subjects, opt.task, raw_data_path, save_data_path, param_dict, \
                        save_pdf=opt.bSavePdf, verbose=opt.bVerbose )


    elif opt.evaluation_single:
        '''
        evaluation with selected feature set 5,6
        '''
        nPoints = param_dict['ROC']['nPoints']
               
        ## br
        save_data_path = os.path.expanduser('~')+\
          '/hrl_file_server/dpark_data/anomaly/TCDS2017/'+opt.task+'_data_adaptation/'+\
          str(param_dict['data_param']['downSampleSize'])+'_'+str(opt.dim)
        ## c11
        save_data_path = os.path.expanduser('~')+\
          '/hrl_file_server/dpark_data/anomaly/TCDS2017/'+opt.task+'_data_adaptation2'
        ## ep
        ## save_data_path = os.path.expanduser('~')+\
        ##   '/hrl_file_server/dpark_data/anomaly/TCDS2017/'+opt.task+'_data_adaptation3'
        ## c8
        ## save_data_path = os.path.expanduser('~')+\
        ##   '/hrl_file_server/dpark_data/anomaly/TCDS2017/'+opt.task+'_data_adaptation4'
        ## c12
        ## save_data_path = os.path.expanduser('~')+\
        ##   '/hrl_file_server/dpark_data/anomaly/TCDS2017/'+opt.task+'_data_adaptation5'
        param_dict['data_param']['handFeatures'] = ['unimodal_audioWristRMS',  \
                                                     'unimodal_kinJntEff_1',\
                                                     'unimodal_ftForce_integ',\
                                                     'crossmodal_landmarkEEDist']
        param_dict['HMM']['scale'] = 5.0
        param_dict['ROC']['progress_param_range'] = -np.logspace(-0.2, 1.4, nPoints)+1.0
        param_dict['ROC']['methods'] = ['progress']

        if opt.bNoUpdate: param_dict['ROC']['update_list'] = []        
        evaluation_single_ad(subjects, opt.task, raw_data_path, save_data_path, param_dict, \
                             save_pdf=opt.bSavePdf, \
                             verbose=opt.bVerbose, debug=opt.bDebug, no_plot=opt.bNoPlot, \
                             find_param=False, data_gen=opt.bDataGen)

        # no adapt: 76


    elif opt.evaluation_double:
        '''
        evaluation...
        '''

        ## c12
        save_data_path = os.path.expanduser('~')+\
          '/hrl_file_server/dpark_data/anomaly/TCDS2017/'+opt.task+'_data_adaptation/'+\
          str(param_dict['data_param']['downSampleSize'])+'_'+str(opt.dim)
        param_dict['ROC']['methods'] = ['progress0', 'progress1']
        param_dict['HMM']['scale']   = [9.0, 9.0]
        param_dict['HMM']['cov']     = 1.0

        param_dict['data_param']['handFeatures'] = [['unimodal_audioWristRMS',  \
                                                    'unimodal_kinJntEff_1',\
                                                    'unimodal_ftForce_integ',\
                                                    'unimodal_kinEEChange',\
                                                    'crossmodal_landmarkEEDist', \
                                                    ],
                                                    ['unimodal_kinVel',\
                                                     'unimodal_ftForce_zero',\
                                                     'crossmodal_landmarkEEDist', \
                                                    ]]
        param_dict['SVM']['hmmgp_logp_offset'] = 0 
        param_dict['ROC']['progress0_param_range'] = -np.logspace(-0.3, 1.3, nPoints)
        param_dict['ROC']['progress1_param_range'] = -np.logspace(-0.3, 1.3, nPoints)
        param_dict['ROC']['hmmgp0_param_range'] = np.logspace(0.2, 2.5, nPoints)*-1.0+1.0
        param_dict['ROC']['hmmgp1_param_range'] = np.logspace(0.2, 2.5, nPoints)*-1.0+0.5 #2.
        # -------------------------------------------------------------------------------------
        
        if opt.bNoUpdate: param_dict['ROC']['update_list'] = []        
        evaluation_double_ad(subjects, opt.task, raw_data_path, save_data_path, param_dict, \
                             save_pdf=opt.bSavePdf, \
                             verbose=opt.bVerbose, debug=opt.bDebug, no_plot=opt.bNoPlot, \
                             find_param=False, data_gen=opt.bDataGen)
