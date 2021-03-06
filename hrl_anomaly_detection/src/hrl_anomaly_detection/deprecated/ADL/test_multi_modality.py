#!/usr/bin/python

import sys, os, copy
import numpy as np, math
import glob
import socket
import time
import random 

import roslib; roslib.load_manifest('hrl_anomaly_detection')
import rospy

# Machine learning library
import mlpy
import scipy as scp
from scipy import interpolate       
from sklearn import preprocessing
from mvpa2.datasets.base import Dataset
from mvpa2.generators.partition import NFoldPartitioner
from mvpa2.generators import splitters
from joblib import Parallel, delayed

# Util
import hrl_lib.util as ut
import matplotlib
import matplotlib.pyplot as pp
import matplotlib.pyplot as plt
import matplotlib.cm as cm
from matplotlib.patches import Polygon
from itertools import product

import data_manager as dm
import sandbox_dpark_darpa_m3.lib.hrl_check_util as hcu
import sandbox_dpark_darpa_m3.lib.hrl_dh_lib as hdl
from hrl_anomaly_detection.HMM.learning_hmm_multi import learning_hmm_multi


tableau20 = [(31, 119, 180), (174, 199, 232), (255, 127, 14), (255, 187, 120),    
             (44, 160, 44), (152, 223, 138), (214, 39, 40), (255, 152, 150),    
             (148, 103, 189), (197, 176, 213), (140, 86, 75), (196, 156, 148),    
             (227, 119, 194), (247, 182, 210), (127, 127, 127), (199, 199, 199),    
             (188, 189, 34), (219, 219, 141), (23, 190, 207), (158, 218, 229)]
tableau20 = np.array(tableau20)/255.0

matplotlib.rcParams['pdf.fonttype'] = 42
matplotlib.rcParams['ps.fonttype'] = 42


def fig_roc(test_title, cross_data_path, nDataSet, onoff_type, check_methods, check_dims, \
            prefix, nState=20, \
            threshold_mult = -1.0*np.arange(0.05, 1.2, 0.05), opr='robot', attr='id', bPlot=False, \
            cov_mult=[1.0, 1.0, 1.0, 1.0], cluster_type='time', \
            renew=False, test=False, disp=None, rm_run=False, sim=False):
    
    # For parallel computing
    strMachine = socket.gethostname()+"_"+str(os.getpid())    
    trans_type = "left_right"
    
    # Check the existance of workspace
    cross_test_path = os.path.join(cross_data_path, str(nState)+'_'+test_title)
    if os.path.isdir(cross_test_path) == False:
        os.system('mkdir -p '+cross_test_path)

    if rm_run == True:                            
        os.system('rm '+os.path.join(cross_test_path, 'running')+'*')
        

    # anomaly check method list
    use_ml_pkl = False
    false_dataSet = None
    count = 0        
    threshold_list = None
        
    for method in check_methods:        
        for i in xrange(nDataSet):
            pkl_file = os.path.join(cross_data_path, "dataSet_"+str(i))
            dd = ut.load_pickle(pkl_file)

            train_aXData1 = dd['ft_force_mag_train_l']
            train_aXData2 = dd['audio_rms_train_l'] 
            train_chunks  = dd['train_chunks']
            test_aXData1  = dd['ft_force_mag_test_l']
            test_aXData2  = dd['audio_rms_test_l'] 
            test_chunks   = dd['test_chunks']

            # min max scaling for training data
            aXData1_scaled, min_c1, max_c1 = dm.scaling(train_aXData1, scale=10.0)
            aXData2_scaled, min_c2, max_c2 = dm.scaling(train_aXData2, scale=10.0)    
            labels = [True]*len(train_aXData1)
            train_dataSet = dm.create_mvpa_dataset(aXData1_scaled, aXData2_scaled, train_chunks, labels)

            # test data!!
            aXData1_scaled, _, _ = dm.scaling(test_aXData1, min_c1, max_c1, scale=10.0)
            aXData2_scaled, _, _ = dm.scaling(test_aXData2, min_c2, max_c2, scale=10.0)    
            labels = [False]*len(test_aXData1)
            test_dataSet = dm.create_mvpa_dataset(aXData1_scaled, aXData2_scaled, test_chunks, labels)

            if sim == True:
                false_aXData1 = dd['ft_force_mag_sim_false_l']
                false_aXData2 = dd['audio_rms_sim_false_l'] 
                false_chunks  = dd['sim_false_chunks']
                false_anomaly_start = dd['anomaly_start_idx']
            
                # generate scaled data!!
                aXData1_scaled, _, _ = dm.scaling(false_aXData1, min_c1, max_c1, scale=10.0)
                aXData2_scaled, _, _ = dm.scaling(false_aXData2, min_c2, max_c2, scale=10.0)    
                labels = [False]*len(false_aXData1)
                false_dataSet = dm.create_mvpa_dataset(aXData1_scaled, aXData2_scaled, false_chunks, labels)
                false_dataSet.sa['anomaly_idx'] = false_anomaly_start
            else:
                false_aXData1 = dd['ft_force_mag_false_l']
                false_aXData2 = dd['audio_rms_false_l'] 
                false_chunks  = dd['false_chunks']
                false_anomaly_start = dd['anomaly_start_idx']                

                # generate scaled data!!
                aXData1_scaled, _, _ = dm.scaling(false_aXData1, min_c1, max_c1, scale=10.0)
                aXData2_scaled, _, _ = dm.scaling(false_aXData2, min_c2, max_c2, scale=10.0)    
                labels = [False]*len(false_aXData1)
                false_dataSet = dm.create_mvpa_dataset(aXData1_scaled, aXData2_scaled, false_chunks, labels)
                false_dataSet.sa['anomaly_idx'] = false_anomaly_start

            for check_dim in check_dims:
            
                lhm = None
                if method == 'globalChange':
                    threshold_list = product(threshold_mult, threshold_mult)
                else:
                    threshold_list = threshold_mult

                # save file name
                res_file = prefix+'_dataset_'+str(i)+'_'+method+'_roc_'+opr+'_dim_'+str(check_dim)+'.pkl'
                mutex_file_part = 'running_dataset_'+str(i)+'_dim_'+str(check_dim)+'_'+method

                res_file = os.path.join(cross_test_path, res_file)
                mutex_file_full = mutex_file_part+'_'+strMachine+'.txt'
                mutex_file      = os.path.join(cross_test_path, mutex_file_full)

                if os.path.isfile(res_file): 
                    count += 1            
                    continue
                elif hcu.is_file(cross_test_path, mutex_file_part): 
                    continue
                ## elif os.path.isfile(mutex_file): continue
                os.system('touch '+mutex_file)

                ret = True
                if lhm is None:
                    if check_dim is not 2:
                        x_train1 = train_dataSet.samples[:,check_dim,:]
                        lhm = learning_hmm_multi(nState=nState, trans_type=trans_type, nEmissionDim=1, \
                                                 check_method=method, cluster_type=cluster_type)
                        if check_dim==0: ret = lhm.fit(x_train1, cov_mult=[cov_mult[0]]*4, use_pkl=use_ml_pkl)
                        elif check_dim==1: ret = lhm.fit(x_train1, cov_mult=[cov_mult[3]]*4, use_pkl=use_ml_pkl)
                    else:
                        x_train1 = train_dataSet.samples[:,0,:]
                        x_train2 = train_dataSet.samples[:,1,:]
                        lhm = learning_hmm_multi(nState=nState, trans_type=trans_type, check_method=method,\
                                                 cluster_type=cluster_type)
                        ret = lhm.fit(x_train1, x_train2, cov_mult=cov_mult, use_pkl=use_ml_pkl)            

                if ret == False:
                    os.system('rm '+mutex_file)
                    sys.exit()

                tp_l = []
                fn_l = []
                fp_l = []
                tn_l = []
                delay_ll = []
                ths_l = []
                        
                for ths in threshold_list:
                            
                    if (disp == 'test' or disp == 'false') and method == 'progress':
                        if disp == 'test':
                            if check_dim == 2:
                                x_test1 = test_dataSet.samples[:,0]
                                x_test2 = test_dataSet.samples[:,1]
                            else:
                                x_test1 = test_dataSet.samples[:,check_dim]
                        elif disp == 'false':
                            if check_dim == 2:
                                x_test1 = false_dataSet.samples[:,0]
                                x_test2 = false_dataSet.samples[:,1]
                            else:
                                x_test1 = false_dataSet.samples[:,check_dim]

                                                
                        lhm.likelihood_disp(x_test1, x_test2, ths, scale1=[min_c1, max_c1, scale], \
                                            scale2=[min_c2, max_c2, scale])
                        

                    if onoff_type == 'online':
                        tp, fn, fp, tn, delay_l,_ = anomaly_check_online_icra(lhm, test_dataSet, \
                                                                            false_dataSet, \
                                                                            ths, \
                                                                            check_dim=check_dim)
                    ## elif onoff_type == 'online':
                    ##     tp, fn, fp, tn, delay_l, _ = anomaly_check_online(lhm, test_dataSet, \
                    ##                                                    false_dataSet, \
                    ##                                                    ths, \
                    ##                                                    check_dim=check_dim)
                    else:
                        tp, fn, fp, tn, delay_l = anomaly_check_offline(lhm, test_dataSet, \
                                                                        false_dataSet, \
                                                                        ths, \
                                                                        check_dim=check_dim)

                    tp_l.append(tp)
                    fn_l.append(fn)
                    fp_l.append(fp)
                    tn_l.append(tn)
                    ths_l.append(ths)
                    delay_ll.append(delay_l)

                d = {}
                d['fn_l']    = fn_l
                d['tn_l']    = tn_l
                d['tp_l']    = tp_l
                d['fp_l']    = fp_l
                d['ths_l']   = ths_l
                d['delay_ll'] = delay_ll

                try:
                    ut.save_pickle(d,res_file)        
                except:
                    print "There is the targeted pkl file"

                os.system('rm '+mutex_file)
                print "-----------------------------------------------"

    if count == len(check_methods)*nDataSet*len(check_dims):
        print "#############################################################################"
        print "All file exist ", count
        print "#############################################################################"        
    else:
        return
        
    if bPlot:

        import itertools
        colors = itertools.cycle(['g', 'm', 'c', 'k'])
        shapes = itertools.cycle(['x','v', 'o', '+'])
        
        fig = pp.figure()

        if len(check_methods) >= len(check_dims): nClass = len(check_methods)
        else: nClass = len(check_dims)

        for n in range(nClass):

            if len(check_methods) >= len(check_dims): 
                method = check_methods[n]
                check_dim = check_dims[0]
            else: 
                method = check_methods[0]
                check_dim = check_dims[n]
                
            if method == 'globalChange':
                threshold_list = list(product(threshold_mult, threshold_mult))
            else:
                threshold_list = threshold_mult
                
            fn_l = np.zeros(len(threshold_list))
            tp_l = np.zeros(len(threshold_list))
            tn_l = np.zeros(len(threshold_list))
            fp_l = np.zeros(len(threshold_list))

            ## delay_l = np.zeros(len(threshold_list)); delay_cnt = np.zeros(len(threshold_list))
            ## err_l = np.zeros(len(threshold_mult));   err_cnt = np.zeros(len(threshold_mult))
                
            for i in xrange(nDataSet):

                # save file name
                res_file = prefix+'_dataset_'+str(i)+'_'+method+'_roc_'+opr+'_dim_'+str(check_dim)+'.pkl'
                res_file = os.path.join(cross_test_path, res_file)

                d = ut.load_pickle(res_file)
                fn_l += np.array(d['fn_l']); tp_l += np.array(d['tp_l']) 
                tn_l += np.array(d['tn_l']); fp_l += np.array(d['fp_l'])
                #delay_l[j] += np.sum(d['delay_ll']); delay_cnt[j] += float(len(d['delay_ll']))  
                
            tpr_l = np.zeros(len(threshold_list))
            fpr_l = np.zeros(len(threshold_list))
            npv_l = np.zeros(len(threshold_list))
            detect_l = np.zeros(len(threshold_list))
                    
            for i in xrange(len(threshold_list)):
                if tp_l[i]+fn_l[i] != 0:
                    tpr_l[i] = tp_l[i]/(tp_l[i]+fn_l[i])*100.0

                if fp_l[i]+tn_l[i] != 0:
                    fpr_l[i] = fp_l[i]/(fp_l[i]+tn_l[i])*100.0

                if tn_l[i]+fn_l[i] != 0:
                    npv_l[i] = tn_l[i]/(tn_l[i]+fn_l[i])*100.0

                ## if delay_cnt[i] == 0:
                ##     delay_l[i] = 0
                ## else:                    
                ##     delay_l[i] = delay_l[i]/delay_cnt[i]

                if tn_l[i] + fn_l[i] + fp_l[i] != 0:
                    detect_l[i] = (tn_l[i]+fn_l[i])/(tn_l[i] + fn_l[i] + fp_l[i])*100.0

            sum_l = tpr_l+fpr_l 
            idx_list = sorted(range(len(sum_l)), key=lambda k: sum_l[k])
            sorted_tpr_l   = np.array([tpr_l[k] for k in idx_list])
            sorted_fpr_l   = np.array([fpr_l[k] for k in idx_list])
            sorted_npv_l   = np.array([npv_l[k] for k in idx_list])
            ## sorted_delay_l = [delay_l[k] for k in idx_list]
            sorted_detect_l = [detect_l[k] for k in idx_list]

            color = colors.next()
            shape = shapes.next()

            ## if i==0: semantic_label='Force only'
            ## elif i==1: semantic_label='Sound only'
            ## else: semantic_label='Force and sound'
            ## pp.plot(sorted_fn_l, sorted_delay_l, '-'+shape+color, label=method, mec=color, ms=8, mew=2)
            ## if method == 'global': label = 'fixed threshold'
            ## if method == 'progress': label = 'progress based threshold'
            ## label = method+"_"+str(check_dim)

            if test_title.find('dim')>=0:
                if check_dim == 0:
                    label = 'Force only'
                elif check_dim == 1:
                    label = 'Sound only'
                elif check_dim == 2:
                    label = 'Force & sound'
                else:
                    label = method +"_"+str(check_dim)                
            else:
                if method == 'globalChange':
                    label = 'Fixed threshold & \n change detection'
                elif method == 'change':
                    label = 'Change detection'
                elif method == 'global':
                    label = 'Fixed threshold \n detection'
                elif method == 'progress':
                    label = 'Dynamic threshold \n detection'
                else:
                    label = method +"_"+str(check_dim)
            
            
            if test:
                pp.plot(sorted_npv_l, sorted_delay_l, '-'+shape+color, label=label, mec=color, ms=8, mew=2)
                ##pp.plot(sorted_detect_l, sorted_delay_l, '-'+shape+color, label=label, mec=color, ms=8, mew=2)
                ##pp.plot(sorted_npv_l, sorted_detect_l, '-'+shape+color, label=label, mec=color, ms=8, mew=2)
            else:
                pp.plot(sorted_fpr_l, sorted_tpr_l, '-'+shape+color, label=label, mec=color, ms=8, mew=2)
                #pp.plot(sorted_ths_l, sorted_tn_l, '-'+shape+color, label=method, mec=color, ms=8, mew=2)



        ## fp_l = fp_l[:,0]
        ## tp_l = tp_l[:,0]
        
        ## from scipy.optimize import curve_fit
        ## def sigma(e, k ,n, offset): return k*((e+offset)**n)
        ## param, var = curve_fit(sigma, fp_l, tp_l)
        ## new_fp_l = np.linspace(fp_l.min(), fp_l.max(), 50)        
        ## pp.plot(new_fp_l, sigma(new_fp_l, *param))

        if test == False:
            pp.xlim([-1, 101])
            pp.ylim([-1, 101])        
            pp.xlabel('False Positive Rate (Percentage)', fontsize=16)
            pp.ylabel('True Positive Rate (Percentage)', fontsize=16)    

        pp.legend(loc=4,prop={'size':16})
        
        fig.savefig('test.pdf')
        fig.savefig('test.png')
        os.system('cp test.p* ~/Dropbox/HRL/')
        #pp.show()
        
    return


def fig_roc_all(cross_root_path, all_task_names, test_title, nState, threshold_mult, check_methods, \
                check_dims, an_type=None, force_an=None, sound_an=None, renew=False, sim=False):
                    
    import itertools
    colors = itertools.cycle(['g', 'm', 'c', 'k'])
    shapes = itertools.cycle(['x','v', 'o', '+'])
    threshold_mult = threshold_mult.tolist()

    tpr_l_fixed = None
    fpr_l_fixed = None
    
    fig = pp.figure()

    if len(check_methods) > len(check_dims): nClass = len(check_methods)
    else: nClass = len(check_dims)

    for n in range(nClass):

        if len(check_methods) > len(check_dims): 
            method = check_methods[n]
            check_dim = check_dims[0]
        else: 
            method = check_methods[0]
            check_dim = check_dims[n]

        if method == 'globalChange':
            threshold_list = list(product(threshold_mult, threshold_mult))
        else:
            threshold_list = threshold_mult
           
        fn_l = np.zeros(len(threshold_list))
        tp_l = np.zeros(len(threshold_list))
        tn_l = np.zeros(len(threshold_list))
        fp_l = np.zeros(len(threshold_list))

        ## delay_l = np.zeros(len(threshold_mult)); delay_cnt = np.zeros(len(threshold_mult))
        ## err_l = np.zeros(len(threshold_mult));   err_cnt = np.zeros(len(threshold_mult))

        if sim:
            save_pkl_file = os.path.join(cross_root_path,test_title+'_'+method+'_'+str(check_dim)+'.pkl')
        else:
            save_pkl_file = os.path.join(cross_root_path,test_title+'_real_'+method+'_'+str(check_dim)+'.pkl')
            
        if os.path.isfile(save_pkl_file) == False:        
            # Collect data
            for task_name in all_task_names:

                if sim:
                    cross_data_path = os.path.join(cross_root_path, 'multi_sim_'+task_name, test_title)
                else:
                    cross_data_path = os.path.join(cross_root_path, 'multi_'+task_name, test_title)

                t_dirs = os.listdir(cross_data_path)
                for t_dir in t_dirs:
                    if t_dir.find(test_title)>=0:
                        break

                cross_test_path = os.path.join(cross_data_path, t_dir)

                pkl_files = sorted([d for d in os.listdir(cross_test_path) if os.path.isfile(os.path.join( \
                    cross_test_path,d))])

                for pkl_file in pkl_files:

                    if pkl_file.find('txt') >= 0:
                        print "There is running file!!!"
                        print cross_test_path
                        res_file = os.path.join(cross_test_path, pkl_file)
                        os.system('rm '+res_file)
                        sys.exit()

                    # method
                    c_method = pkl_file.split('_roc')[0].split('_')[-1]
                    if c_method != method: continue
                    # dim
                    c_dim = int(pkl_file.split('dim_')[-1].split('.pkl')[0])
                    if c_dim != check_dim: continue

                    res_file = os.path.join(cross_test_path, pkl_file)
                    d = ut.load_pickle(res_file)

                    ths_l = d['ths_l']

                    ## for ths in ths_l:
                            
                    ##     # find close index
                    ##     for i, t_thres in enumerate(threshold_list):

                    ##         if c_method == 'globalChange':
                    ##             if abs(t_thres[0] - ths[0]) < 0.00001 and abs(t_thres[1] - ths[1]) < 0.00001:
                    ##                 idx = i
                    ##                 break
                    ##         else:
                    ##             if abs(t_thres - ths) < 0.00001:
                    ##                 idx = i
                    ##                 break

                    fn_l += np.array(d['fn_l']); tp_l += np.array(d['tp_l']) 
                    tn_l += np.array(d['tn_l']); fp_l += np.array(d['fp_l'])                                
                    ## delay_l[idx] += np.sum(d['delay_l']); delay_cnt[idx] += float(len(d['delay_l']))  
                            
            data = {}
            data['fn_l'] = fn_l
            data['tp_l'] = tp_l
            data['tn_l'] = tn_l
            data['fp_l'] = fp_l
            ## data['delay_l'] = delay_l
            ## data['delay_cnt'] = delay_cnt
            ut.save_pickle(data, save_pkl_file)
        else:
            data = ut.load_pickle(save_pkl_file)
            fn_l = data['fn_l']
            tp_l = data['tp_l'] 
            tn_l = data['tn_l'] 
            fp_l = data['fp_l'] 
            ## delay_l = data['delay_l'] 
            ## delay_cnt = data['delay_cnt'] 
                

        tpr_l = np.zeros(len(threshold_list))
        fpr_l = np.zeros(len(threshold_list))
        npv_l = np.zeros(len(threshold_list))
        detect_l = np.zeros(len(threshold_list))

        for i in xrange(len(threshold_list)):
            if tp_l[i]+fn_l[i] != 0:
                tpr_l[i] = tp_l[i]/(tp_l[i]+fn_l[i])*100.0

            if fp_l[i]+tn_l[i] != 0:
                fpr_l[i] = fp_l[i]/(fp_l[i]+tn_l[i])*100.0

            if tn_l[i]+fn_l[i] != 0:
                npv_l[i] = tn_l[i]/(tn_l[i]+fn_l[i])*100.0

            ## if delay_cnt[i] == 0:
            ##     delay_l[i] = 0
            ## else:                    
            ##     delay_l[i] = delay_l[i]/delay_cnt[i]

            if tn_l[i] + fn_l[i] + fp_l[i] != 0:
                detect_l[i] = (tn_l[i]+fn_l[i])/(tn_l[i] + fn_l[i] + fp_l[i])*100.0
                
        sum_l = tpr_l+fpr_l 
        idx_list = sorted(range(len(sum_l)), key=lambda k: sum_l[k])
        sorted_tpr_l   = np.array([tpr_l[k] for k in idx_list])
        sorted_fpr_l   = np.array([fpr_l[k] for k in idx_list])
        sorted_npv_l   = np.array([npv_l[k] for k in idx_list])
        ## sorted_delay_l = [delay_l[k] for k in idx_list]
        sorted_detect_l = [detect_l[k] for k in idx_list]

        if method == 'global':
            tpr_l_fixed = sorted_tpr_l
            fpr_l_fixed = sorted_fpr_l
            
        color = colors.next()
        shape = shapes.next()

        if test_title.find('dim')>=0:
            if check_dim == 0:
                label = 'Force only'
            elif check_dim == 1:
                label = 'Audio only'
            elif check_dim == 2:
                label = 'Force & audio'
            else:
                label = method +"_"+str(check_dim)                
        else:
            if method == 'globalChange':
                label = 'Fixed threshold & \n change detection'
            elif method == 'change':
                label = 'Change detection'
            elif method == 'global':
                label = 'Fixed threshold \n detection'
            elif method == 'progress':
                label = 'Dynamic threshold \n detection'
            else:
                label = method +"_"+str(check_dim)

        if method == 'globalChange':                

            xl = []
            yl = []
            for x,y in zip(sorted_fpr_l, sorted_tpr_l):

                min_idx = 0
                min_dist = 1000
                for i, (tx, ty) in enumerate(zip(fpr_l_fixed, tpr_l_fixed)):
                    if min_dist > (tx-x)**2 + (ty-y)**2:
                        min_idx  = i
                        min_dist = (tx-x)**2 + (ty-y)**2

                if min_idx == 0 or min_idx == len(fpr_l_fixed)-1: continue

                try:
                    a1 = (tpr_l_fixed[min_idx] - tpr_l_fixed[min_idx-1]) / (fpr_l_fixed[min_idx] - fpr_l_fixed[min_idx-1])
                    b1 = tpr_l_fixed[min_idx] - a1*fpr_l_fixed[min_idx]

                    a2 = (tpr_l_fixed[min_idx+1] - tpr_l_fixed[min_idx]) / (fpr_l_fixed[min_idx+1] - fpr_l_fixed[min_idx])
                    b2 = tpr_l_fixed[min_idx+1] - a2*fpr_l_fixed[min_idx+1]
                except:
                    continue
                
                if y - (a1*x + b1) > 0 or y - (a2*x + b2) > 0:
                    xl.append(x)
                    yl.append(y)
            
            pp.plot(xl, yl, '-'+shape+color, label=label, mec=color, ms=8, mew=2)
        else:
            pp.plot(sorted_fpr_l, sorted_tpr_l, '-'+shape+color, label=label, mec=color, ms=8, mew=2)

    pp.legend(loc=4,prop={'size':16})
    pp.xlabel('False Positive Rate (Percentage)', fontsize=16)
    pp.ylabel('True Positive Rate (Percentage)', fontsize=16)    

    fig.savefig('test.pdf')
    fig.savefig('test.png')
    os.system('cp test.p* ~/Dropbox/HRL/')
    ## pp.show()
 
       
#---------------------------------------------------------------------------------------#        
def fig_eval(test_title, cross_data_path, nDataSet, onoff_type, check_methods, check_dims, \
             prefix, nState=20, \
             opr='robot', attr='id', bPlot=False, \
             cov_mult=[1.0, 1.0, 1.0, 1.0], renew=False, test=False, disp=None, rm_run=False, sim=False, 
             detect_break=False):
    
    # For parallel computing
    strMachine = socket.gethostname()+"_"+str(os.getpid())    
    trans_type = "left_right"
    
    # Check the existance of workspace
    cross_test_path = os.path.join(cross_data_path, str(nState)+'_'+test_title)
    if os.path.isdir(cross_test_path) == False:
        os.system('mkdir -p '+cross_test_path)

    if rm_run == True:                            
        os.system('rm '+os.path.join(cross_test_path, 'running')+'*')
        
    # anomaly check method list
    use_ml_pkl = False
    false_dataSet = None
    count = 0        
    
    for method in check_methods:        
        for i in xrange(nDataSet):

            pkl_file = os.path.join(cross_data_path, "dataSet_"+str(i))
            dd = ut.load_pickle(pkl_file)

            train_aXData1 = dd['ft_force_mag_train_l']
            train_aXData2 = dd['audio_rms_train_l'] 
            train_chunks  = dd['train_chunks']
            test_aXData1 = dd['ft_force_mag_test_l']
            test_aXData2 = dd['audio_rms_test_l'] 
            test_chunks  = dd['test_chunks']

            # min max scaling for training data
            aXData1_scaled, min_c1, max_c1 = dm.scaling(train_aXData1, scale=10.0)
            aXData2_scaled, min_c2, max_c2 = dm.scaling(train_aXData2, scale=10.0)    
            labels = [True]*len(train_aXData1)
            train_dataSet = dm.create_mvpa_dataset(aXData1_scaled, aXData2_scaled, train_chunks, labels)

            # test data!!
            aXData1_scaled, _, _ = dm.scaling(test_aXData1, min_c1, max_c1, scale=10.0)
            aXData2_scaled, _, _ = dm.scaling(test_aXData2, min_c2, max_c2, scale=10.0)    
            labels = [False]*len(test_aXData1)
            test_dataSet = dm.create_mvpa_dataset(aXData1_scaled, aXData2_scaled, test_chunks, labels)

            if sim == True:
                false_aXData1 = dd['ft_force_mag_sim_false_l']
                false_aXData2 = dd['audio_rms_sim_false_l'] 
                false_chunks  = dd['sim_false_chunks']            
            else:
                false_aXData1 = dd['ft_force_mag_false_l']
                false_aXData2 = dd['audio_rms_false_l'] 
                false_chunks  = dd['false_chunks']

            ## print np.shape(false_aXData1), np.shape(false_aXData2)
                ## print false_chunks
                ## for k in xrange(len(false_aXData2)):
                ##     print np.shape(false_aXData1[k]), np.shape(false_aXData2[k])
                
            false_anomaly_start = dd['anomaly_start_idx']                
            false_peak    = dd.get('anomaly_peak',[])
            false_width   = dd.get('anomaly_width',[])

            # generate simulated data!!
            aXData1_scaled, _, _ = dm.scaling(false_aXData1, min_c1, max_c1, scale=10.0)
            aXData2_scaled, _, _ = dm.scaling(false_aXData2, min_c2, max_c2, scale=10.0)    
            labels = [False]*len(false_aXData1)
            false_dataSet = dm.create_mvpa_dataset(aXData1_scaled, aXData2_scaled, false_chunks, labels)
            false_dataSet.sa['anomaly_idx']   = false_anomaly_start
            false_dataSet.sa['anomaly_peak']  = false_peak
            false_dataSet.sa['anomaly_width'] = false_width
                

            for check_dim in check_dims:
            
                # save file name
                res_file = prefix+'_dataset_'+str(i)+'_'+method+'_roc_'+opr+'_dim_'+str(check_dim)+'.pkl'
                res_file = os.path.join(cross_test_path, res_file)

                mutex_file_part = 'running_dataset_'+str(i)+'_dim_'+str(check_dim)+'_'+method
                mutex_file_full = mutex_file_part+'_'+strMachine+'.txt'
                mutex_file      = os.path.join(cross_test_path, mutex_file_full)

                if os.path.isfile(res_file): 
                    count += 1            
                    continue
                elif hcu.is_file(cross_test_path, mutex_file_part): 
                    continue
                ## elif os.path.isfile(mutex_file): continue
                os.system('touch '+mutex_file)

                ret = True
                x_train1 = None
                x_train2 = None
                if check_dim is not 2:
                    x_train1 = train_dataSet.samples[:,check_dim,:]
                    lhm = learning_hmm_multi(nState=nState, trans_type=trans_type, nEmissionDim=1, \
                                             check_method=method)
                    if check_dim==0: ret = lhm.fit(x_train1, cov_mult=[cov_mult[0]]*4, use_pkl=use_ml_pkl)
                    elif check_dim==1: ret = lhm.fit(x_train1, cov_mult=[cov_mult[3]]*4, use_pkl=use_ml_pkl)
                else:
                    x_train1 = train_dataSet.samples[:,0,:]
                    x_train2 = train_dataSet.samples[:,1,:]                        
                    ## plot_all(x_train1, x_train2)

                    lhm = learning_hmm_multi(nState=nState, trans_type=trans_type, check_method=method)
                    ret = lhm.fit(x_train1, x_train2, cov_mult=cov_mult, use_pkl=use_ml_pkl)            

                if ret == False:
                    print mutex_file
                    # need to delete data and previous results with the dataset
                    os.system('rm '+pkl_file)
                    res_file = os.path.join(cross_test_path,prefix+'_dataset_'+str(i))
                    os.system('rm '+res_file+'_*.pkl')
                    os.system('rm '+mutex_file)
                    sys.exit()
                    

                # find a minimum sensitivity gain
                if check_dim == 2:
                    x_test1 = test_dataSet.samples[:,0]
                    x_test2 = test_dataSet.samples[:,1]
                else:
                    x_test1 = test_dataSet.samples[:,check_dim]

                min_ths, min_ind = lhm.get_sensitivity_gain_batch(x_test1, x_test2)

                # temp--------------------------------------------------------
                min_ths2, min_ind2 = lhm.get_sensitivity_gain_batch(x_train1, x_train2)
                if type(min_ths) == list or type(min_ths)==np.ndarray: 
                    print type(min_ths), min_ths
                    for j in xrange(len(min_ths)):
                        if min_ths[j] > min_ths2[j]: min_ths[j] = min_ths2[j]
                else:
                    if min_ths > min_ths2: min_ths = min_ths2
                
                
                if False:      
                    for j in xrange(len(false_chunks)):                     
                        if check_dim == 2:
                            x_test1 = np.array([false_dataSet.samples[j:j+1,0][0]])
                            x_test2 = np.array([false_dataSet.samples[j:j+1,1][0]])
                        else:
                            x_test1 = np.array([false_dataSet.samples[j:j+1,check_dim][0]])

                        print np.shape(x_test1), np.shape(x_test2)
                            
                        lhm.likelihood_disp(x_test1, x_test2, min_ths, scale1=[min_c1, max_c1, scale], \
                                            scale2=[min_c2, max_c2, scale])

                            
                tn_peak_l = []
                tn_width_l = []
                tn_chunk_l = []
                                            
                if onoff_type == 'online':
                    tp, fn, fp, tn, delay_l, false_detection_l = anomaly_check_online(lhm, [], \
                                                                                      false_dataSet, \
                                                                                      min_ths, \
                                                                                      check_dim=check_dim, \
                                                                                      peak_l=tn_peak_l, \
                                                                                      width_l=tn_width_l, \
                                                                                      chunk_l=tn_chunk_l, \
                                                                                      detect_break=detect_break)
                                                                                      
                else:
                    tp, fn, fp, tn, delay_l = anomaly_check_offline(lhm, [], \
                                                                    false_dataSet, \
                                                                    min_ths, \
                                                                    check_dim=check_dim, \
                                                                    peak_l=tn_peak_l, \
                                                                    width_l=tn_width_l, \
                                                                    chunk_l=tn_chunk_l)


                d = {}
                d['fn']    = fn
                d['tn']    = tn
                d['tp']    = tp
                d['fp']    = fp
                d['ths']   = min_ths
                d['delay_l'] = delay_l
                d['peak_l']  = tn_peak_l
                d['width_l'] = tn_width_l
                d['chunk_l'] = tn_chunk_l
                d['false_detection_l'] = false_detection_l

                try:
                    ut.save_pickle(d,res_file)        
                except:
                    print "There is the targeted pkl file"

                os.system('rm '+mutex_file)
                print "-----------------------------------------------"

    if count == len(check_methods)*(nDataSet)*len(check_dims):
        print "#############################################################################"
        print "All file exist ", count
        print "#############################################################################"        
    else:
        return
        
    
    if bPlot:

        slope_discrete_class_l = []
        delay_avg_class_l = []
        delay_std_class_l = []

        slope_fdr_avg_class_l = []
        slope_fdr_std_class_l = []
        
        fig = pp.figure()       
        for midx, method in enumerate(check_methods):        
        
            fn_l = np.zeros(nDataSet)
            tp_l = np.zeros(nDataSet)
            tn_l = np.zeros(nDataSet)
            fp_l = np.zeros(nDataSet)
            fd_l = []
            fpr_l = np.zeros(nDataSet)
            delay_l = []
            peak_l = []
            width_l = []
            chunk_l = []

            for i in xrange(nDataSet):
                # save file name
                res_file = prefix+'_dataset_'+str(i)+'_'+method+'_roc_'+opr+'_dim_'+str(check_dim)+'.pkl'
                res_file = os.path.join(cross_test_path, res_file)

                d = ut.load_pickle(res_file)
                fn_l[i] = d['fn']; tp_l[i] = d['tp'] 
                tn_l[i] = d['tn']; fp_l[i] = d['fp'] 
                fd_l.append([d['false_detection_l']])
                ## print d['false_detection_l']

                if d['delay_l'] == []: continue
                else:
                    if delay_l == []: 
                        if d.get('delay_l',[]) == [[]] or d.get('delay_l',[]) == []: 
                            delay_l = [-1]
                        else:
                            delay_l = d.get('delay_l',[-1])
                        peak_l  = d.get('peak_l',[])
                        width_l = d.get('width_l',[])
                        chunk_l = d.get('chunk_l',[])
                    else:
                        if d.get('delay_l',[]) == [[]] or  d.get('delay_l',[]) == []: 
                            delay_l += [-1]
                        else:
                            delay_l += d.get('delay_l',[-1])                        
                        peak_l  += d.get('peak_l',[])
                        width_l += d.get('width_l',[])
                        chunk_l += d.get('chunk_l',[])
                    
                
            for i in xrange(nDataSet):
                if fp_l[i]+tn_l[i] != 0:
                    fpr_l[i] = fp_l[i]/(fp_l[i]+tn_l[i])*100.0

            tot_fpr = np.sum(fp_l)/(np.sum(fp_l)+np.sum(tn_l))*100.0

            if test_title.find('param') < 0:            
                pp.bar(range(nDataSet+1), np.hstack([fpr_l,np.array([tot_fpr])]))            
                pp.ylim([0.0, 100])                                  
            elif True:

                ## print len(delay_l) , " : ", delay_l
                ## print "--------------"
                ## print len(width_l), " : ", width_l
                ## print fd_l
                ## sys.exit()
                
                slope_a = np.array(peak_l)/(np.array(width_l)/freq)
                if test_title.find('force') >= 0:
                    print "Force check"
                    slope_discrete =  np.arange(0.0, np.amax(slope_a)+0.5, 150.0) +75.0
                else:
                    print "Sound check with max : ", np.amax(slope_a)
                    slope_discrete =  np.arange(0.0, np.amax(slope_a)+0.001, 0.07) +0.035

                delay_raw_l = []
                delay_avg_l = np.zeros(len(slope_discrete))
                delay_std_l = np.zeros(len(slope_discrete))
                    
                slope_fd_raw_l=[]                    
                slope_fdr_avg_l = np.zeros(len(slope_discrete))
                slope_fdr_std_l = np.zeros(len(slope_discrete))
                    
                for i in xrange(len(slope_discrete)):
                    delay_raw_l.append([])
                    slope_fd_raw_l.append([])

                for i, s in enumerate(slope_a):
                    idx = (np.abs(slope_discrete-s)).argmin()                    
                    delay_raw_l[idx].append(delay_l[i])
                    slope_fd_raw_l[idx].append(fd_l[i])

                for i in xrange(len(delay_raw_l)):
                    if len(delay_raw_l[i]) > 0:
                        delay_raws = filter(lambda x: x != -1, delay_raw_l[i])
                        if len(delay_raws) > 0:                         
                            delay_avg_l[i] = np.mean(np.array(delay_raws)/freq)
                            delay_std_l[i] = np.std(np.array(delay_raws)/freq)                    
                    if len(slope_fd_raw_l[i])>0:
                        slope_fdr_avg_l[i] = np.mean(np.array(slope_fd_raw_l[i])*100.0)
                        slope_fdr_std_l[i] = np.std(np.array(slope_fd_raw_l[i])*100.0)

                slope_discrete_class_l.append(slope_discrete)
                delay_avg_class_l.append(delay_avg_l)
                delay_std_class_l.append(delay_std_l)

                slope_fdr_avg_class_l.append(slope_fdr_avg_l)
                slope_fdr_std_class_l.append(slope_fdr_std_l)

                width = 0.2
                ind = np.arange(len(slope_discrete_class_l[0]))+width/2.0
                        
                ax1 =pp.subplot(211)        
                if midx == 0:
                    rects1 = pp.bar(ind, slope_fdr_avg_class_l[0], width, color=tableau20[0])
                elif midx == 1:                   
                    rects2 = pp.bar(ind+width, slope_fdr_avg_class_l[1], width, color=tableau20[2])
                elif midx == 2:                   
                    rects3 = pp.bar(ind+2.*width, slope_fdr_avg_class_l[2], width, color=tableau20[4])
                elif midx == 3:                   
                    rects4 = pp.bar(ind+3.*width, slope_fdr_avg_class_l[3], width, color=tableau20[6])
                pp.ylim([0.0, 100.0])
                pp.ylabel('Detection Rate [%]', fontsize=16)    

                ax2 =pp.subplot(212)
                if midx == 0:                
                    rects1 = pp.bar(ind, delay_avg_class_l[0], width, color=tableau20[0], 
                                    yerr=delay_std_class_l[0], label=check_methods[0])
                elif midx == 1:
                    rects2 = pp.bar(ind+width, delay_avg_class_l[1], width, color=tableau20[2], 
                                    yerr=delay_std_class_l[1], label=check_methods[1])
                elif midx == 2:
                    rects3 = pp.bar(ind+2.*width, delay_avg_class_l[2], width, color=tableau20[4], 
                                    yerr=delay_std_class_l[2], label=check_methods[2])
                elif midx == 3:
                    rects4 = pp.bar(ind+3.*width, delay_avg_class_l[3], width, color=tableau20[6], 
                                    yerr=delay_std_class_l[3], label=check_methods[3])
                pp.ylabel('Delay Time [sec]', fontsize=16)    
                if test_title.find('force') >= 0:
                    pp.ylim([0.0, 0.9])
                else:
                    pp.ylim([0.0, 0.8])
                
                
            else:                                
                slope_arr = np.array(peak_l)/(np.array(width_l)/freq)
                ## pp.plot(np.array(delay_l)/freq, np.array(width_l)/freq , 'r.')
                pp.plot(slope_arr, np.array(delay_l)/freq, 'r.')
                pp.xlabel('Slope', fontsize=16)
                pp.ylabel('Delay', fontsize=16)
        
        fig.savefig('test.pdf')
        fig.savefig('test.png')
        os.system('cp test.p* ~/Dropbox/HRL/')
        ## pp.show()

        
        



#---------------------------------------------------------------------------------------#    
def fig_eval_all(cross_root_path, all_task_names, test_title, nState, check_methods, \
                 check_dims, an_type=None, force_an=None, sound_an=None, renew=False, sim=False):
                    
    if len(check_methods) >= len(check_dims): nClass = len(check_methods)
    else: nClass = len(check_dims)
    fdr_mu_class_l = []
    fdr_std_class_l = []

    delay_class_l = []
    peak_class_l = []
    width_class_l = []
    chunk_class_l = []

    delay_time_class_l = []
    slope_avg_class_l = []
    slope_std_class_l = []

    peak_avg_class_l = []
    peak_std_class_l = []

    width_avg_class_l = []
    width_std_class_l = []

    slope_discrete_class_l = []
    delay_avg_class_l = []
    delay_std_class_l = []

    slope_fdr_avg_class_l = []
    slope_fdr_std_class_l = []
        
    for n in range(nClass):

        if len(check_methods) >= len(check_dims): 
            method = check_methods[n]
            check_dim = check_dims[0]
        else: 
            method = check_methods[0]
            check_dim = check_dims[n]

        fn_l = np.zeros(len(all_task_names))
        tp_l = np.zeros(len(all_task_names))
        tn_l = np.zeros(len(all_task_names))
        fp_l = np.zeros(len(all_task_names))
        fdr_l = np.zeros(len(all_task_names)) # false detection rate
        fd_l = []
        delay_l = []
        peak_l = []
        width_l = []
        chunk_l = []
        slope_fdr_l = []

        ## tot_fd_sum = 0
        ## tot_fd_cnt = 0

        if sim:
            save_pkl_file = os.path.join(cross_root_path,test_title+'_'+method+'_'+str(check_dim)+'.pkl')
        else:
            save_pkl_file = os.path.join(cross_root_path,test_title+'_real_'+method+'_'+str(check_dim)+'.pkl')

        if os.path.isfile(save_pkl_file) == False or renew==True:        
            # Collect data
            for task_num, task_name in enumerate(all_task_names):

                if sim:
                    cross_data_path = os.path.join(cross_root_path, 'multi_sim_'+task_name, test_title)
                else:
                    cross_data_path = os.path.join(cross_root_path, 'multi_'+task_name, test_title)

                t_dirs = os.listdir(cross_data_path)
                for t_dir in t_dirs:
                    if t_dir.find(test_title)>=0:
                        break

                cross_test_path = os.path.join(cross_data_path, t_dir)

                pkl_files = sorted([d for d in os.listdir(cross_test_path) if os.path.isfile(os.path.join( \
                    cross_test_path,d))])

                fd_sum = 0
                fd_cnt = 0

                for pkl_file in pkl_files:

                    if pkl_file.find('txt') >= 0:
                        print "There is running file!!!"
                        print cross_test_path
                        res_file = os.path.join(cross_test_path, pkl_file)
                        os.system('rm '+res_file)
                        sys.exit()

                    # method
                    c_method = pkl_file.split('_roc')[0].split('_')[-1]
                    if c_method != method: continue
                    # dim
                    c_dim = int(pkl_file.split('dim_')[-1].split('.pkl')[0])
                    if c_dim != check_dim: continue

                    res_file = os.path.join(cross_test_path, pkl_file)

                    d = ut.load_pickle(res_file)
                    fn_l[task_num] += d['fn']; tp_l[task_num] += d['tp'] 
                    tn_l[task_num] += d['tn']; fp_l[task_num] += d['fp'] 

                    fd_sum += np.sum(d['false_detection_l'])
                    fd_cnt += len(d['false_detection_l'])
                    
                    if delay_l == []: 
                        if d.get('delay_l',[]) == [[]]: 
                            delay_l = [-1]
                        else:
                            delay_l = d.get('delay_l',[-1])
                        peak_l  = d.get('peak_l',[])
                        width_l = d.get('width_l',[])
                        chunk_l = d.get('chunk_l',[])
                        fd_l    = d['false_detection_l'].tolist()
                    else:
                        if d.get('delay_l',[]) == [[]]: 
                            delay_l += [-1]
                        else:
                            delay_l += d.get('delay_l',[-1])                        
                        peak_l  += d.get('peak_l',[])
                        width_l += d.get('width_l',[])
                        chunk_l += d.get('chunk_l',[])
                        fd_l    += d['false_detection_l'].tolist()                            

                    ## print task_num, d['false_detection_l']
                    ## fdr_l[task_num] = d['false_detection_l']
                    ## print c_method, ": ", float(np.sum(d['false_detection_l'])) / float(len(d['false_detection_l']))                    

                if float(fd_cnt) == 0.0:
                    print cross_test_path
                    print c_method, task_num
                    sys.exit()
                fdr_l[task_num] = float(fd_sum) / float(fd_cnt)

                ## tot_fd_sum += float(fd_sum)
                ## tot_fd_cnt += float(fd_cnt)

            print method, " : ", fdr_l

            if peak_l != []:
            
                delay_time =  np.arange(0.0, np.amax(delay_l)+1.00001, 2.0) /freq
                peak_cnt_l  = np.zeros(len(delay_time))
                slope_avg_l = np.zeros(len(delay_time))
                slope_std_l = np.zeros(len(delay_time))

                peak_avg_l = np.zeros(len(delay_time))
                peak_std_l = np.zeros(len(delay_time))
                width_avg_l = np.zeros(len(delay_time))
                width_std_l = np.zeros(len(delay_time))

                slope_raw_l = []
                peak_raw_l = []
                width_raw_l = []
                for i in xrange(len(delay_time)):
                    slope_raw_l.append([])
                    peak_raw_l.append([])
                    width_raw_l.append([])

                ## print len(delay_l), len(peak_l)

                for i,d in enumerate(delay_l): 
                    ## slope_raw_l[d].append(peak_l[i]/width_l[i]/freq) 
                    slope_raw_l[d/2].append(peak_l[i]/(width_l[i]/freq)) 
                    peak_raw_l[d/2].append(peak_l[i])
                    width_raw_l[d/2].append(width_l[i]/freq)

                for i in xrange(len(slope_raw_l)):                

                    if len(slope_raw_l[i]) > 0:
                        slope_avg_l[i] = np.mean(slope_raw_l[i])
                        slope_std_l[i] = np.std(slope_raw_l[i])

                        peak_avg_l[i] = np.mean(peak_raw_l[i])
                        peak_std_l[i] = np.std(peak_raw_l[i])

                        width_avg_l[i] = np.mean(width_raw_l[i])
                        width_std_l[i] = np.std(width_raw_l[i])


                # delay distribution per slope (0~1.0)
                slope_a = np.array(peak_l)/(np.array(width_l)/freq)
                if test_title.find('force') >= 0:
                    print "Force check"
                    slope_discrete =  np.arange(0.0, np.amax(slope_a)+0.5, 150.0) +75.0
                else:
                    print "Sound check with max : ", np.amax(slope_a)
                    slope_discrete =  np.arange(0.0, np.amax(slope_a)+0.001, 0.07) +0.035
                    
                delay_raw_l = []
                delay_avg_l = np.zeros(len(slope_discrete))
                delay_std_l = np.zeros(len(slope_discrete))

                slope_fd_raw_l=[]
                slope_fdr_avg_l = np.zeros(len(slope_discrete))
                slope_fdr_std_l = np.zeros(len(slope_discrete))

                ## print len(slope_discrete), np.amax(slope_a)

                for i in xrange(len(slope_discrete)):
                    delay_raw_l.append([])
                    slope_fd_raw_l.append([])

                ## print len(delay_raw_l), len(slope_fd_raw_l)

                for i, s in enumerate(slope_a):
                    idx = (np.abs(slope_discrete-s)).argmin()
                    delay_raw_l[idx].append(delay_l[i])
                    slope_fd_raw_l[idx].append(fd_l[i])


                for i in xrange(len(delay_raw_l)):
                    if len(delay_raw_l[i]) > 0:
                        delay_raws = filter(lambda x: x != -1, delay_raw_l[i])
                        if len(delay_raws) > 0:
                            delay_avg_l[i] = np.mean(np.array(delay_raws)/freq)
                            delay_std_l[i] = np.std(np.array(delay_raws)/freq)                    
                    if len(slope_fd_raw_l[i])>0:
                        slope_fdr_avg_l[i] = np.mean(np.array(slope_fd_raw_l[i])*100.0)
                        slope_fdr_std_l[i] = np.std(np.array(slope_fd_raw_l[i])*100.0)
                    
            data = {}
            data['fn_l'] = fn_l
            data['tp_l'] = tp_l
            data['tn_l'] = tn_l
            data['fp_l'] = fp_l
            data['fdr_l'] = fdr_l
            data['tot_fdr_mu'] = tot_fdr_mu = np.mean(fdr_l*100)
            data['tot_fdr_std'] = tot_fdr_std = np.std(fdr_l*100)

            if peak_l != []:            
                data['delay_l'] = delay_l
                data['peak_l']  = peak_l
                data['width_l'] = width_l
                data['chunk_l'] = chunk_l

                data['delay_time'] = delay_time
                data['slope_avg'] = slope_avg_l
                data['slope_std'] = slope_std_l
                data['peak_avg'] = peak_avg_l
                data['peak_std'] = peak_std_l
                data['width_avg'] = width_avg_l
                data['width_std'] = width_std_l

                data['slope_discrete'] = slope_discrete
                data['delay_avg'] = delay_avg_l
                data['delay_std'] = delay_std_l

                data['slope_fdr_avg'] = slope_fdr_avg_l
                data['slope_fdr_std'] = slope_fdr_std_l

            ut.save_pickle(data, save_pkl_file)
            
        else:
            data = ut.load_pickle(save_pkl_file)
            fn_l = data['fn_l']
            tp_l = data['tp_l'] 
            tn_l = data['tn_l'] 
            fp_l = data['fp_l'] 
            fdr_l = data['fdr_l'] 
            tot_fdr_mu  = data['tot_fdr_mu']
            tot_fdr_std = data['tot_fdr_std']

            delay_l = data.get('delay_l',[])
            peak_l  = data.get('peak_l',[])
            width_l = data.get('width_l',[])
            chunk_l = data.get('chunk_l',[])

            delay_time = data.get('delay_time',[])
            slope_avg_l = data.get('slope_avg',[]) 
            slope_std_l = data.get('slope_std',[]) 

            peak_avg_l = data.get('peak_avg',[]) 
            peak_std_l = data.get('peak_std',[]) 
            width_avg_l = data.get('width_avg',[]) 
            width_std_l = data.get('width_std',[]) 

            slope_discrete = data.get('slope_discrete',[])
            delay_avg_l = data.get('delay_avg',[])
            delay_std_l = data.get('delay_std',[])
            
            slope_fdr_avg_l = data.get('slope_fdr_avg',[])
            slope_fdr_std_l = data.get('slope_fdr_std',[])
            
            
        fdr_mu_class_l.append(tot_fdr_mu)
        fdr_std_class_l.append(tot_fdr_std)

        if peak_l != []:
            delay_class_l.append(delay_l)
            peak_class_l.append(peak_l)
            width_class_l.append(width_l)
            chunk_class_l.append(chunk_l)

            delay_time_class_l.append(delay_time)
            slope_avg_class_l.append(slope_avg_l)
            slope_std_class_l.append(slope_std_l)

            peak_avg_class_l.append(peak_avg_l)
            peak_std_class_l.append(peak_std_l)

            width_avg_class_l.append(width_avg_l)
            width_std_class_l.append(width_std_l)

            slope_discrete_class_l.append(slope_discrete)
            delay_avg_class_l.append(delay_avg_l)
            delay_std_class_l.append(delay_std_l)

            slope_fdr_avg_class_l.append(slope_fdr_avg_l)
            slope_fdr_std_class_l.append(slope_fdr_std_l)

    import itertools
    colors = itertools.cycle(['g', 'm', 'c', 'k'])
    shapes = itertools.cycle(['x','v', 'o', '+'])
        
    ind = np.arange(nClass)*0.9
    width = 0.5
    methods = ('Change \n detection', 'Fixed threshold \n detection', 'Fixed threshold \n & change detection', \
               'Dynamic threshold \n detection')

    print fdr_mu_class_l
    
    if test_title.find('param') < 0 :            
        fig = pp.figure()

        pp.bar(ind + width/4.0, fdr_mu_class_l, width, color=[tableau20[0],tableau20[2],
                                                              tableau20[4],tableau20[6]], 
                                                              yerr=fdr_std_class_l)
    
        pp.ylabel('Anomaly Detection Rate (Percentage)', fontsize=16)    
        ## pp.xlabel('False Positive Rate (Percentage)', fontsize=16)
        pp.xticks(ind + width*3.0/4, methods )
        pp.ylim([0.0, 100])                           
        
    elif True:

        width = 0.2
        ind = np.arange(len(slope_discrete_class_l[0]))+width/2.0

        fig = pp.figure()
        ax1 =pp.subplot(211)        
        rects1 = pp.bar(ind, slope_fdr_avg_class_l[0], width, color=tableau20[0])
        rects2 = pp.bar(ind+width, slope_fdr_avg_class_l[1], width, color=tableau20[2])
        rects3 = pp.bar(ind+2.*width, slope_fdr_avg_class_l[2], width, color=tableau20[4])
        rects4 = pp.bar(ind+3.*width, slope_fdr_avg_class_l[3], width, color=tableau20[6])
        pp.ylim([0.0, 100.0])
        pp.ylabel('Detection Rate [%]', fontsize=16)    
        xlabel_l = []
        for i, s in enumerate(slope_discrete):
            xlabel_l.append(str(s-slope_discrete[0])+' ~ '+str(s+slope_discrete[0]))
        pp.xticks(ind+width*2.0,xlabel_l)
        
        ax2 =pp.subplot(212)
        rects1 = pp.bar(ind, delay_avg_class_l[0], width, color=tableau20[0], 
                        yerr=delay_std_class_l[0], label=methods[0])
        rects2 = pp.bar(ind+width, delay_avg_class_l[1], width, color=tableau20[2], 
                        yerr=delay_std_class_l[1], label=methods[1])
        rects3 = pp.bar(ind+2.*width, delay_avg_class_l[2], width, color=tableau20[4], 
                        yerr=delay_std_class_l[2], label=methods[2])
        rects4 = pp.bar(ind+3.*width, delay_avg_class_l[3], width, color=tableau20[6], 
                        yerr=delay_std_class_l[3], label=methods[3])
        pp.ylabel('Delay Time [sec]', fontsize=16)    
        if test_title.find('force') >= 0:
            pp.ylim([0.0, 0.6])
        else:
            pp.ylim([0.0, 0.8])

        xlabel_l = []
        for i, s in enumerate(slope_discrete):
            xlabel_l.append(str(s-slope_discrete[0])+' ~ '+str(s+slope_discrete[0]))
        pp.xticks(ind+width*2.0,xlabel_l)
        if test_title.find('force') >= 0:
            pp.xlabel('Peak[N]/Width[sec]', fontsize=16) 
        else:
            pp.xlabel('Peak[RMS]/Width[sec]', fontsize=16) 
                
        pp.legend(loc='upper right',prop={'size':8}, fancybox=True, shadow=True, ncol=2)       
       
    else:
        fig = pp.figure()
        
        for i, delay_time_l in enumerate(delay_time_class_l):

            color = colors.next()
            shape = shapes.next()
        
            ## pp.plot(np.array(delay_class_l[i])/freq, \
            ##         np.array(peak_class_l[i])/(np.array(width_class_l[i])/freq), color+shape,label=methods[i])

            pp.plot(np.array(delay_class_l[i])/freq, \
                    np.array(peak_class_l[i]), color+shape,label=methods[i])
                    
            
        pp.xlabel('Detection Time [sec]', fontsize=16)
        pp.ylabel('Peak [N]', fontsize=16)
        ## pp.ylabel('Width', fontsize=16)
        ## pp.ylabel('Peak/Width', fontsize=16)
        pp.legend(loc='upper right',prop={'size':8}, fancybox=True, shadow=True, ncol=4)       
        pp.xlim([-0.05, 3.0])

        

    fig.savefig('test.pdf')
    fig.savefig('test.png')
    os.system('cp test.p* ~/Dropbox/HRL/')
    ## pp.show()


#---------------------------------------------------------------------------------------#        
def animation(test_title, cross_data_path, nDataSet, onoff_type, check_methods, check_dims, \
              prefix, nState=20, \
              opr='robot', attr='id', cov_mult=[1.0, 1.0, 1.0, 1.0], sim=False, true_data=False):
    
    # For parallel computing
    strMachine = socket.gethostname()+"_"+str(os.getpid())    
    trans_type = "left_right"
    
    # Check the existance of workspace
    cross_test_path = os.path.join(cross_data_path, str(nState)+'_'+test_title)
    if os.path.isdir(cross_test_path) == False:
        os.system('mkdir -p '+cross_test_path)

    # anomaly check method list
    false_dataSet = None
    count = 0        
    
    for method in check_methods:        
        for i in xrange(nDataSet):

            pkl_file = os.path.join(cross_data_path, "dataSet_"+str(i))
            dd = ut.load_pickle(pkl_file)

            train_aXData1 = dd['ft_force_mag_train_l']
            train_aXData2 = dd['audio_rms_train_l'] 
            train_chunks  = dd['train_chunks']
            test_aXData1 = dd['ft_force_mag_test_l']
            test_aXData2 = dd['audio_rms_test_l'] 
            test_chunks  = dd['test_chunks']

            # min max scaling for training data
            aXData1_scaled, min_c1, max_c1 = dm.scaling(train_aXData1, scale=10.0)
            aXData2_scaled, min_c2, max_c2 = dm.scaling(train_aXData2, scale=10.0)    
            labels = [True]*len(train_aXData1)
            train_dataSet = dm.create_mvpa_dataset(aXData1_scaled, aXData2_scaled, train_chunks, labels)

            # test data!!
            aXData1_scaled, _, _ = dm.scaling(test_aXData1, min_c1, max_c1, scale=10.0)
            aXData2_scaled, _, _ = dm.scaling(test_aXData2, min_c2, max_c2, scale=10.0)    
            labels = [False]*len(test_aXData1)
            test_dataSet = dm.create_mvpa_dataset(aXData1_scaled, aXData2_scaled, test_chunks, labels)

            if sim == True:
                false_aXData1 = dd['ft_force_mag_sim_false_l']
                false_aXData2 = dd['audio_rms_sim_false_l'] 
                false_chunks  = dd['sim_false_chunks']
                false_anomaly_start = dd['anomaly_start_idx']
            
                # generate simulated data!!
                aXData1_scaled, _, _ = dm.scaling(false_aXData1, min_c1, max_c1, scale=10.0)
                aXData2_scaled, _, _ = dm.scaling(false_aXData2, min_c2, max_c2, scale=10.0)    
                labels = [False]*len(false_aXData1)
                false_dataSet = dm.create_mvpa_dataset(aXData1_scaled, aXData2_scaled, false_chunks, labels)
                false_dataSet.sa['anomaly_idx'] = false_anomaly_start
            else:
                false_aXData1 = dd['ft_force_mag_false_l']
                false_aXData2 = dd['audio_rms_false_l'] 
                false_chunks  = dd['false_chunks']
                false_anomaly_start = dd['anomaly_start_idx']                

                ## print np.shape(false_aXData1), np.shape(false_aXData2)
                ## print false_chunks
                ## for k in xrange(len(false_aXData2)):
                ##     print np.shape(false_aXData1[k]), np.shape(false_aXData2[k])

                aXData1_scaled, _, _ = dm.scaling(false_aXData1, min_c1, max_c1, scale=10.0)
                aXData2_scaled, _, _ = dm.scaling(false_aXData2, min_c2, max_c2, scale=10.0)    
                labels = [False]*len(false_aXData1)
                false_dataSet = dm.create_mvpa_dataset(aXData1_scaled, aXData2_scaled, false_chunks, labels)
                false_dataSet.sa['anomaly_idx'] = false_anomaly_start

            for check_dim in check_dims:
            
                if check_dim is not 2:
                    x_train1 = train_dataSet.samples[:,check_dim,:]
                    lhm = learning_hmm_multi(nState=nState, trans_type=trans_type, nEmissionDim=1, \
                                             check_method=method)
                    if check_dim==0: lhm.fit(x_train1, cov_mult=[cov_mult[0]]*4, use_pkl=False)
                    elif check_dim==1: lhm.fit(x_train1, cov_mult=[cov_mult[3]]*4, use_pkl=False)
                else:
                    x_train1 = train_dataSet.samples[:,0,:]
                    x_train2 = train_dataSet.samples[:,1,:]                        
                    ## plot_all(x_train1, x_train2)

                    lhm = learning_hmm_multi(nState=nState, trans_type=trans_type, check_method=method)
                    lhm.fit(x_train1, x_train2, cov_mult=cov_mult, use_pkl=False)            

                # find a minimum sensitivity gain
                if check_dim == 2:
                    x_test1 = test_dataSet.samples[:,0]
                    x_test2 = test_dataSet.samples[:,1]
                else:
                    x_test1 = test_dataSet.samples[:,check_dim]

                min_ths = 0
                min_ind = 0
                if method == 'progress':
                    min_ths = np.zeros(lhm.nGaussian)+10000
                    min_ind = np.zeros(lhm.nGaussian)
                elif method == 'globalChange':
                    min_ths = np.zeros(2)+10000
                    
                n = len(x_test1)
                for i in range(n):
                    m = len(x_test1[i])

                    # anomaly_check only returns anomaly cases only
                    for j in range(2,m):                    

                        if check_dim == 2:            
                            ths, ind = lhm.get_sensitivity_gain(x_test1[i][:j], x_test2[i][:j])   
                        else:
                            ths, ind = lhm.get_sensitivity_gain(x_test1[i][:j])

                        if ths == []: continue

                        if method == 'progress':
                            if min_ths[ind] > ths:
                                min_ths[ind] = ths
                                ## print "Minimum threshold: ", min_ths[ind], ind                                
                        elif method == 'globalChange':
                            if min_ths[0] > ths[0]:
                                min_ths[0] = ths[0]
                            if min_ths[1] > ths[1]:
                                min_ths[1] = ths[1]
                            ## print "Minimum threshold: ", min_ths[0], min_ths[1] 
                        else:
                            if min_ths > ths:
                                min_ths = ths
                                ## print "Minimum threshold: ", min_ths

                if true_data==False:
                    if check_dim == 2:
                        x_test1 = false_dataSet.samples[:,0]
                        x_test2 = false_dataSet.samples[:,1]
                    else:
                        x_test1 = false_dataSet.samples[:,check_dim]

                n = len(x_test1)
                for i in range(n):
                    print "Visualize : ", i
                    if i != 1: continue
                    lhm.simulation(x_test1[i], x_test2[i], min_ths, bSave=True)
    
#-------------------------------------------------------------------------------------------------------
def fig_roc_offline(cross_data_path, \
                    true_aXData1, true_aXData2, true_chunks, \
                    false_aXData1, false_aXData2, false_chunks, \
                    prefix, nState=20, \
                    threshold_mult = np.arange(0.05, 1.2, 0.05), opr='robot', attr='id', bPlot=False, \
                    cov_mult=[1.0, 1.0, 1.0, 1.0]):

    # For parallel computing
    strMachine = socket.gethostname()+"_"+str(os.getpid())    
    trans_type = "left_right"
    
    # Check the existance of workspace
    cross_test_path = os.path.join(cross_data_path, str(nState))
    if os.path.isdir(cross_test_path) == False:
        os.system('mkdir -p '+cross_test_path)

    # min max scaling for true data
    aXData1_scaled, min_c1, max_c1 = dm.scaling(true_aXData1, scale=10.0)
    aXData2_scaled, min_c2, max_c2 = dm.scaling(true_aXData2, scale=10.0)    
    labels = [True]*len(true_aXData1)
    true_dataSet = dm.create_mvpa_dataset(aXData1_scaled, aXData2_scaled, true_chunks, labels)
    print "Scaling data: ", np.shape(true_aXData1), " => ", np.shape(aXData1_scaled)
    
    # min max scaling for false data
    aXData1_scaled, _, _ = dm.scaling(false_aXData1, min_c1, max_c1, scale=10.0, verbose=True)
    aXData2_scaled, _, _ = dm.scaling(false_aXData2, min_c2, max_c2, scale=10.0)    
    labels = [False]*len(false_aXData1)
    false_dataSet = dm.create_mvpa_dataset(aXData1_scaled, aXData2_scaled, false_chunks, labels)

    # K random training-test set
    splits = []
    for i in xrange(40):
        test_dataSet  = Dataset.random_samples(true_dataSet, len(false_aXData1))
        train_ids = [val for val in true_dataSet.sa.id if val not in test_dataSet.sa.id] 
        train_ids = Dataset.get_samples_by_attr(true_dataSet, 'id', train_ids)
        train_dataSet = true_dataSet[train_ids]
        splits.append([train_dataSet, test_dataSet])
        
    ## Multi dimension
    for i in xrange(3):
        count = 0
        for ths in threshold_mult:

            # save file name
            res_file = prefix+'_roc_'+opr+'_dim_'+str(i)+'_ths_'+str(ths)+'.pkl'
            res_file = os.path.join(cross_test_path, res_file)

            mutex_file_part = 'running_dim_'+str(i)+'_ths_'+str(ths)
            mutex_file_full = mutex_file_part+'_'+strMachine+'.txt'
            mutex_file      = os.path.join(cross_test_path, mutex_file_full)

            if os.path.isfile(res_file): 
                count += 1            
                continue
            elif hcu.is_file(cross_test_path, mutex_file_part): continue
            elif os.path.isfile(mutex_file): continue
            os.system('touch '+mutex_file)

            print "---------------------------------"
            print "Total splits: ", len(splits)


            ## fn_ll = []
            ## tn_ll = []
            ## fn_err_ll = []
            ## tn_err_ll = []
            ## for j, (l_wdata, l_vdata) in enumerate(splits):
            ##     fn_ll, tn_ll, fn_err_ll, tn_err_ll = anomaly_check_offline(j, l_wdata, l_vdata, nState, \
            ##                                                            trans_type, ths, false_dataSet, \
            ##                                                            check_dim=i)
            ##     print np.mean(fn_ll), np.mean(tn_ll)
            ## sys.exit()
                                  
            n_jobs = -1
            r = Parallel(n_jobs=n_jobs)(delayed(anomaly_check_offline)(j, l_wdata, l_vdata, nState, \
                                                                       trans_type, ths, false_dataSet, \
                                                                       cov_mult=cov_mult, check_dim=i) \
                                        for j, (l_wdata, l_vdata) in enumerate(splits))
            fn_ll, tn_ll, fn_err_ll, tn_err_ll = zip(*r)

            import operator
            fn_l = reduce(operator.add, fn_ll)
            tn_l = reduce(operator.add, tn_ll)
            fn_err_l = reduce(operator.add, fn_err_ll)
            tn_err_l = reduce(operator.add, tn_err_ll)

            d = {}
            d['fn']  = np.mean(fn_l)
            d['tp']  = 1.0 - np.mean(fn_l)
            d['tn']  = np.mean(tn_l)
            d['fp']  = 1.0 - np.mean(tn_l)

            if fn_err_l == []:         
                d['fn_err'] = 0.0
            else:
                d['fn_err'] = np.mean(fn_err_l)

            if tn_err_l == []:         
                d['tn_err'] = 0.0
            else:
                d['tn_err'] = np.mean(tn_err_l)

            ut.save_pickle(d,res_file)        
            os.system('rm '+mutex_file)
            print "-----------------------------------------------"

        if count == len(threshold_mult):
            print "#############################################################################"
            print "All file exist ", count
            print "#############################################################################"        

        
    if count == len(threshold_mult) and bPlot:

        import itertools
        colors = itertools.cycle(['g', 'm', 'c', 'k'])
        shapes = itertools.cycle(['x','v', 'o', '+'])
        
        fig = pp.figure()
        
        for i in xrange(3):
            fp_l = []
            tp_l = []
            err_l = []
            for ths in threshold_mult:
                res_file   = prefix+'_roc_'+opr+'_dim_'+str(i)+'_'+'ths_'+str(ths)+'.pkl'
                res_file   = os.path.join(cross_test_path, res_file)

                d = ut.load_pickle(res_file)
                tp  = d['tp'] 
                fn  = d['fn'] 
                fp  = d['fp'] 
                tn  = d['tn'] 
                fn_err = d['fn_err']         
                tn_err = d['tn_err']         

                fp_l.append([fp])
                tp_l.append([tp])
                err_l.append([fn_err])

            fp_l  = np.array(fp_l)*100.0
            tp_l  = np.array(tp_l)*100.0

            color = colors.next()
            shape = shapes.next()
            semantic_label='likelihood detection \n with known mechanism class '+str(i)
            pp.plot(fp_l, tp_l, shape+color, label= semantic_label, mec=color, ms=8, mew=2)



        ## fp_l = fp_l[:,0]
        ## tp_l = tp_l[:,0]
        
        ## from scipy.optimize import curve_fit
        ## def sigma(e, k ,n, offset): return k*((e+offset)**n)
        ## param, var = curve_fit(sigma, fp_l, tp_l)
        ## new_fp_l = np.linspace(fp_l.min(), fp_l.max(), 50)        
        ## pp.plot(new_fp_l, sigma(new_fp_l, *param))

        
        pp.xlabel('False positive rate (percentage)')
        pp.ylabel('True positive rate (percentage)')    
        ## pp.xlim([0, 30])
        pp.legend(loc=1,prop={'size':14})
        
        pp.show()
                            
    return

    ########################################################################################    



def anomaly_check_offline(lhm, test_dataSet, false_dataSet, ths, check_dim=2, 
                          peak_l=None, width_l=None, chunk_l=None):

    tp = 0.0
    fn = 0.0
    fp = 0.0
    tn = 0.0
    
    err_l = []
    delay_l = []

    # 1) Use True data to get true negative rate
    if test_dataSet != []:    
        if check_dim == 2:
            x_test1 = test_dataSet.samples[:,0]
            x_test2 = test_dataSet.samples[:,1]
        else:
            x_test1 = test_dataSet.samples[:,check_dim]

        n = len(x_test1)
        for i in range(n):
            # anomaly_check only returns anomaly cases only
            if check_dim == 2:            
                an, err = lhm.anomaly_check(x_test1[i], x_test2[i], ths_mult=ths)   
            else:
                an, err = lhm.anomaly_check(x_test1[i], ths_mult=ths)           

            if an == 1.0:   fn += 1.0
            elif an == 0.0: tp += 1.0
    
    # 2) Use False data to get true negative rate
    if false_dataSet != []:
        if check_dim == 2:
            x_test1 = false_dataSet.samples[:,0]
            x_test2 = false_dataSet.samples[:,1]
        else:
            x_test1 = false_dataSet.samples[:,check_dim]
        anomaly_idx = false_dataSet.sa.anomaly_idx
        
        n = len(x_test1)
        for i in range(n):

            # anomaly_check only returns anomaly cases only
            delay = 0
            if check_dim == 2:            
                an, err = lhm.anomaly_check(x_test1[i], x_test2[i], ths_mult=ths)   
            else:
                an, err = lhm.anomaly_check(x_test1[i], ths_mult=ths)           

            if an == 1.0:   tn += 1.0
            elif an == 0.0: fp += 1.0

            if peak_l is not None and width_l is not None:
                print "Not implemented!!"
                sys.exit()
                        
    return tp, fn, fp, tn, delay_l


def anomaly_check_online(lhm, test_dataSet, false_dataSet, ths, check_dim=2, 
                         peak_l=None, width_l=None, chunk_l=None, detect_break=False):

    tp = 0.0
    fn = 0.0
    fp = 0.0
    tn = 0.0
    
    err_l = []
    delay_l = []
    false_detection_l = []

    # 1) Use True data to get true negative rate
    if test_dataSet != []:    
        if check_dim == 2:
            x_test1 = test_dataSet.samples[:,0]
            x_test2 = test_dataSet.samples[:,1]
        else:
            x_test1 = test_dataSet.samples[:,check_dim]

        n = len(x_test1)
        for i in range(n):
            m = len(x_test1[i])

            # anomaly_check only returns anomaly cases only
            for j in range(2,m):                    

                if check_dim == 2:            
                    an, err = lhm.anomaly_check(x_test1[i][:j], x_test2[i][:j], ths_mult=ths)   
                else:
                    an, err = lhm.anomaly_check(x_test1[i][:j], ths_mult=ths)           

                if an == 1.0:   fn += 1.0
                elif an == 0.0: tp += 1.0

                
    # 2) Use False data to get true negative rate
    if false_dataSet != []:
        if check_dim == 2:
            x_test1 = false_dataSet.samples[:,0]
            x_test2 = false_dataSet.samples[:,1]
        else:
            x_test1 = false_dataSet.samples[:,check_dim]
        anomaly_idx  = false_dataSet.sa.anomaly_idx
            
        n = len(x_test1)
        false_detection_l = np.zeros(n)
        
        
        for i in range(n):
            m = len(x_test1[i])
            delay_l.append([])

            # simulated anomaly info
            if peak_l is not None and width_l is not None:
                peak_l.append(false_dataSet.sa.anomaly_peak)
                width_l.append(false_dataSet.sa.anomaly_width)
            if chunk_l is not None:
                chunk_l.append(false_dataSet.sa.chunks)
            
            # anomaly_check only returns anomaly cases only
            delay = 0
            for j in range(2,m):                    

                if check_dim == 2:            
                    an, err = lhm.anomaly_check(x_test1[i][:j], x_test2[i][:j], ths_mult=ths)   
                else:
                    an, err = lhm.anomaly_check(x_test1[i][:j], ths_mult=ths)           

                delay = j-anomaly_idx[i]

                if delay >= 0:
                    if an == 1.0:
                        tn += 1.0
                        
                        delay_l[-1] = delay
                        false_detection_l[i] = True                                                
                        if detect_break: break
                            
                    elif an == 0.0:
                        fp += 1.0
                else:
                    if an == 1.0:
                        fn += 1.0
                    elif an == 0.0:
                        tp += 1.0    
                    ## err_l.append(err)
                    
                # If this is not simulated anomaly
                if peak_l is None and an == 1.0:
                    false_detection_l[i] = True                                                
            

    return tp, fn, fp, tn, delay_l, false_detection_l


def anomaly_check_online_icra(lhm, test_dataSet, false_dataSet, ths, check_dim=2, peak_l=None, width_l=None):

    tp = 0.0
    fn = 0.0
    fp = 0.0
    tn = 0.0
    
    err_l = []
    delay_l = []
    false_detection_l = []

    # 1) Use True data to get true negative rate
    if test_dataSet != []:    
        if check_dim == 2:
            x_test1 = test_dataSet.samples[:,0]
            x_test2 = test_dataSet.samples[:,1]
        else:
            x_test1 = test_dataSet.samples[:,check_dim]

        n = len(x_test1)
        for i in range(n):
            m = len(x_test1[i])
            anomaly = False

            # anomaly_check only returns anomaly cases only
            for j in range(2,m):                    

                if check_dim == 2:            
                    an, err = lhm.anomaly_check(x_test1[i][:j], x_test2[i][:j], ths_mult=ths)   
                else:
                    an, err = lhm.anomaly_check(x_test1[i][:j], ths_mult=ths)           

                if an==1.0: 
                    anomaly=True
                    break

            if anomaly is True:
                fp += 1.0
            else:                
                tn += 1.0

                
    # 2) Use False data to get true negative rate
    if false_dataSet != []:
        if check_dim == 2:
            x_test1 = false_dataSet.samples[:,0]
            x_test2 = false_dataSet.samples[:,1]
        else:
            x_test1 = false_dataSet.samples[:,check_dim]
        anomaly_idx  = false_dataSet.sa.anomaly_idx
            
        n = len(x_test1)
        false_detection_l = np.zeros(n)
                
        for i in range(n):
            m = len(x_test1[i])

            # anomaly_check only returns anomaly cases only
            anomaly = False
            for j in range(2,m):                    

                if check_dim == 2:            
                    an, err = lhm.anomaly_check(x_test1[i][:j], x_test2[i][:j], ths_mult=ths)   
                else:
                    an, err = lhm.anomaly_check(x_test1[i][:j], ths_mult=ths)           

                if an == 1.0:
                    anomaly=True
                    break

            if anomaly == True:
                tp += 1.0
            else:
                fn += 1.0        
            
    return tp, fn, fp, tn, [], []
    
    
    
def anomaly_check(i, l_wdata, l_vdata, nState, trans_type, ths):

    # Cross validation
    x_train1 = l_wdata.samples[:,0,:]
    x_train2 = l_wdata.samples[:,1,:]

    lhm = learning_hmm_multi(nState=nState, trans_type=trans_type)
    lhm.fit(x_train1, x_train2)

    x_test1 = l_vdata.samples[:,0,:]
    x_test2 = l_vdata.samples[:,1,:]
    n,m = np.shape(x_test1)
    
    fp_l  = []
    err_l = []
    for i in range(n):
        for j in range(2,m,1):
            fp, err = lhm.anomaly_check(x_test1[i:i+1,:j], x_test2[i:i+1,:j], ths_mult=ths)           
            fp_l.append(fp)
            if err != 0.0: err_l.append(err)
                
    return fp_l, err_l
    

    

def plot_audio(time_list, data_list, title=None, chunk=1024, rate=44100.0, max_int=32768.0 ):

    import librosa
    from librosa import feature


    data_seq = data_list.flatten()
    t = np.arange(0.0, len(data_seq), 1.0)/rate    
    
    # find init
    pp.figure()
    ax1 =pp.subplot(411)
    pp.plot(t, data_seq)
    ## pp.plot(time_list, data_list)
    ## pp.stem([idx_start, idx_end], [f[idx_start], f[idx_end]], 'k-*', bottom=0)
    ax1.set_xlim([0, t[-1]])
    if title is not None: pp.title(title)


    #========== Spectrogram =========================
    from matplotlib.mlab import complex_spectrum, specgram, magnitude_spectrum
    ax = pp.subplot(412)        
    pp.specgram(data_seq, NFFT=chunk, Fs=rate)
    ax.set_ylim([0,5000])
    ax = pp.subplot(413)       
    S = librosa.feature.melspectrogram(data_seq, sr=rate, n_fft=chunk, n_mels=30)
    log_S = librosa.logamplitude(S, ref_power=np.max)
    librosa.display.specshow(log_S, sr=rate, hop_length=8, x_axis='time', y_axis='mel')
    ## ax.set_ylim([0,5000])

    ## ax = pp.subplot(414)            
    ## bands = np.arange(0, 10) * 100
    ## hists = []
    ## for i, data in enumerate(data_list):        


    ##     S = librosa.feature.melspectrogram(data, sr=rate, n_fft=chunk, n_mels=30, fmin=100, fmax=5000)
    ##     log_S = librosa.logamplitude(S, ref_power=np.max)
        
    ##     ## new_data = np.hstack([data/max_int, np.zeros(len(data))]) # zero padding
    ##     ## fft = np.fft.fft(new_data)  # FFT          
    ##     ## fftr=10*np.log10(abs(fft.real))[:len(new_data)/2]
    ##     ## freq=np.fft.fftfreq(np.arange(len(new_data)).shape[-1])[:len(new_data)/2]
        
    ##     ## ## print fftr.shape, freq.shape
    ##     ## hists.append(S[:,1])
    ##     if hists == []:
    ##         hists = log_S[:,1:2]
    ##     else:
    ##         hists = np.hstack([hists, log_S[:,1:2]])
    ##     print log_S.shape, S.shape, hists.shape

    ##     ## #count bin
    ##     ## hist, hin_edges = np.histogram(freq, weights=fftr, bins=bands, density=True)
    ##     ## hists.append(hist)
        
    ## pp.imshow(hists, origin='down')
        
        

        
    #========== RMS =========================
    ax2 = pp.subplot(414)    
    rms_list = []
    for i, data in enumerate(data_list):
        rms_list.append(get_rms(data))
    t = np.arange(0.0, len(data_list), 1.0)*chunk/rate    
    pp.plot(t, rms_list) 

    #========== MFCC =========================
    ax = pp.subplot(412)
    mfcc_feat = librosa.feature.mfcc(data_seq, n_mfcc=4, sr=rate, n_fft=1024)
    ## mfcc_feat = feature.mfcc(data_list, sr=rate, n_mfcc=13, n_fft=1024, )
    pp.imshow(mfcc_feat, origin='down')
    ## ax.set_xlim([0, t[-1]*100])

    ax = pp.subplot(413)
    S = feature.melspectrogram(data_list, sr=rate, n_fft=1024, hop_length=1, n_mels=128)
    log_S = librosa.logamplitude(S, ref_power=np.max)        
    ## mfcc_feat = librosa.feature.mfcc(S=log_S, n_mfcc=20, sr=rate, n_fft=1024)
    mfcc_feat = librosa.feature.delta(mfcc_feat)
    pp.imshow(mfcc_feat, origin='down')

    ax = pp.subplot(414)
    mfcc_feat = librosa.feature.delta(mfcc_feat, order=2)
    pp.imshow(mfcc_feat, origin='down')

    
    
    
    ## librosa.display.specshow(log_S, sr=rate, hop_length=256, x_axis='time', y_axis='mel')

    ## print log_S.shape
    
    ## pp.psd(data_list, NFFT=chunk, Fs=rate, noverlap=0)    
    ## complex_spectrum(data_list, Fs=rate)
    ## ax2.set_xlim([0, t[-1]])
    ## ax2.set_ylim([0, 30000])
    
    
    ## from features import mfcc, logfbank        
    ## mfcc_feat = mfcc(data_list, rate, numcep=13)
    ## ax4 = pp.subplot(414)
    ## pp.imshow(mfcc_feat.T, origin='down')
    ## ax4.set_xlim([0, t[-1]*100])

    ## ax4 = pp.subplot(414)
    ## fbank_feat = logfbank(data_list, rate, winlen=float(chunk)/rate, nfft=chunk, lowfreq=10, highfreq=3000)    
    ## pp.imshow(fbank_feat.T, origin='down')
    ## ax4.set_xlim([0, t[-1]*100])



    
    ## pp.subplot(412)
    ## for k in xrange(len(audio_data_cut)):            
    ##     cur_time = time_range + audio_time_cut[0] + float(k)*1024.0/44100.0
    ##     pp.plot(cur_time, audio_data_cut[k], 'b.')

    ## pp.subplot(413)
    ## pp.plot(audio_time_cut, np.mean((np.array(audio_data_cut)),axis=1))

    ## pp.subplot(414)
    ## pp.plot(audio_time_cut, np.std((np.array(audio_data_cut)),axis=1))
    ## pp.stem([idx_start, idx_end], [max(audio_data_l[i][idx_start]), max(audio_data_l[i][idx_end])], 'k-*', bottom=0)
    ## pp.title(names[i])
    ## pp.plot(audio_freq_l[i], audio_amp_l[i])
    pp.show()


def plot_one(data1, data2, false_data1=None, false_data2=None, data_idx=0, labels=None, freq=43.0):

    fig = pp.figure()
    plt.rc('text', usetex=True)
    
    ax1 = pp.subplot(211)
    if false_data1 is None:
        data = data1[data_idx]
    else:
        data = false_data1[data_idx]        

    x   = np.arange(0., float(len(data))) * (1./freq)
        
    pp.plot(x, data, 'b', linewidth=1.5, label='Force')
    #ax1.set_xlim([0, len(data)])
    ax1.set_ylim([0, np.amax(data)*1.1])
    pp.grid()
    ax1.set_ylabel("Magnitude [N]", fontsize=18)

        
    ax2 = pp.subplot(212)
    if false_data2 is None:
        data = data2[data_idx]
    else:
        data = false_data2[data_idx]
    
    pp.plot(x, data, 'b', linewidth=1.5, label='Sound')
    #ax2.set_xlim([0, len(data)])
    pp.grid()
    ax2.set_ylabel("Energy", fontsize=18)
    ax2.set_xlabel("Time [sec]", fontsize=18)
    
    ax1.legend(prop={'size':18})
    ax2.legend(prop={'size':18})
    
    fig.savefig('test.pdf')
    fig.savefig('test.png')
    pp.show()

    

    
def plot_all(data1, data2, false_data1=None, false_data2=None, labels=None, distribution=False, freq=43.0):

        ## # find init
        ## pp.figure()
        ## pp.subplot(211)
        ## pp.plot(f)
        ## pp.stem([idx_start, idx_end], [f[idx_start], f[idx_end]], 'k-*', bottom=0)
        ## pp.title(names[i])
        ## pp.subplot(212)
        ## pp.plot(force[2,:])
        ## pp.show()
        
        ## plot_audio(audio_time_cut, audio_data_cut, chunk=CHUNK, rate=RATE, title=names[i])

    def vectors_to_mean_sigma(vecs):
        data = np.array(vecs)
        m,n = np.shape(data)
        mu  = np.zeros(n)
        sig = np.zeros(n)
        
        for i in xrange(n):
            mu[i]  = np.mean(data[:,i])
            sig[i] = np.std(data[:,i])
        
        return mu, sig


    if false_data1 is None:
        data = data1[0]
    else:
        data = false_data1[0]                
    x   = np.arange(0., float(len(data))) * (1./freq)
        
        
    fig = pp.figure()
    plt.rc('text', usetex=True)

    #-----------------------------------------------------------------
    ax1 = pp.subplot(211)
    if distribution:
        x       = range(len(data1[0]))
        mu, sig = vectors_to_mean_sigma(data1)        
        ax1.fill_between(x, mu-sig, mu+sig, facecolor='green', edgecolor='1.0', \
                         alpha=0.5, interpolate=True)            
    else:
        for i, d in enumerate(data1):
            if not(labels is not None and labels[i] == False):
                true_line, = pp.plot(x, d, label='Normal data')

    # False data
    if false_data1 is not None:
        for i, d in enumerate(false_data1):
            x = np.array(range(len(d))) 
            pp.plot(x, d, color='k', linewidth=1.0)
                
    ## # False data
    ## for i, d in enumerate(data1):
    ##     if labels is not None and labels[i] == False:
    ##         pp.plot(d, label=str(i), color='k', linewidth=1.0)
    ax1.set_ylabel("Force Magnitude [N]", fontsize=18)

    ## true_line = ax1.plot([], [], color='green', alpha=0.5, linewidth=10, label='Normal data') #fake for legend
    ## false_line = ax1.plot([], [], color='k', linewidth=10, label='Abnormal data') #fake for legend    
    ## ax1.legend()

        
    #-----------------------------------------------------------------
    ax2 = pp.subplot(212)
    if distribution:
        x       = range(len(data2[0]))
        mu, sig = vectors_to_mean_sigma(data2)        
        ax2.fill_between(x, mu-sig, mu+sig, facecolor='green', edgecolor='1.0', \
                         alpha=0.5, interpolate=True)            
    else:        
        for i, d in enumerate(data2):
            if not(labels is not None and labels[i] == False):
                pp.plot(x, d)

    # for false data
    if false_data2 is not None:
        for i, d in enumerate(false_data2):
            x = np.array(range(len(d)))            
            pp.plot(x, d, color='k', linewidth=1.0)
            
    ax2.set_ylabel("Sound Energy", fontsize=18)
    ax2.set_xlabel("Time step [sec]", fontsize=18)

    ## true_line = ax2.plot([], [], color='green', alpha=0.5, linewidth=10, label='Normal data') #fake for legend
    ## false_line = ax2.plot([], [], color='k', linewidth=10, label='Abnormal data') #fake for legend
    ## ax2.legend()

    fig.savefig('test.pdf')
    fig.savefig('test.png')    
    os.system('cp test.p* ~/Dropbox/HRL/')
    ## pp.show()
    
    


if __name__ == '__main__':

    import optparse
    p = optparse.OptionParser()
    p.add_option('--renew', action='store_true', dest='bRenew',
                 default=False, help='Renew pickle files.')
    p.add_option('--roc_online_simulated_dim_check', '--ronsimdim', action='store_true', \
                 dest='bRocOnlineSimDimCheck', default=False, 
                 help='Plot online ROC by simulated anomaly form dim comparison')    
    p.add_option('--roc_online_simulated_method_check', '--ronsimmthd', action='store_true', \
                 dest='bRocOnlineSimMethodCheck',
                 default=False, help='Plot online ROC by simulated anomaly')    
    p.add_option('--roc_online_dim_check', '--rondim', action='store_true', \
                 dest='bRocOnlineDimCheck',
                 default=False, help='Plot online ROC by real anomaly with dimension check')    
    p.add_option('--roc_online_method_check', '--ronmthd', action='store_true', \
                 dest='bRocOnlineMethodCheck',
                 default=False, help='Plot online ROC by real anomaly')    
    p.add_option('--roc_offline_method_check', '--roffmthd', action='store_true', \
                 dest='bRocOfflineMethodCheck',
                 default=False, help='Plot offline ROC by real anomaly')    
    p.add_option('--roc_offline_dim_check', '--roffdim', action='store_true', \
                 dest='bRocOfflineDimCheck',
                 default=False, help='Plot offline ROC by real anomaly with dimension check')    
    p.add_option('--online_method_check', '--omc', action='store_true', \
                 dest='bOnlineMethodCheck',
                 default=False, help='Plot offline ROC by real anomaly')    

    p.add_option('--online_simulated_method_param_check', '--ronsimmthdp', '--test', action='store_true', \
                 dest='bOnlineSimMethodParamCheck',
                 default=False, help='Plot online ROC by simulated anomaly')    
    
    p.add_option('--all_plot', '--all', action='store_true', dest='bAllPlot',
                 default=False, help='Plot all data')
    p.add_option('--one_plot', '--one', action='store_true', dest='bOnePlot',
                 default=False, help='Plot one data')
    p.add_option('--plot', '--p', action='store_true', dest='bPlot',
                 default=False, help='Plot')
    p.add_option('--rm_running', '--rr', action='store_true', dest='bRemoveRunning',
                 default=False, help='Remove all the running files')
    p.add_option('--animation', '--ani', action='store_true', dest='bAnimation',
                 default=False, help='Plot by time using animation')
    p.add_option('--path_disp', '--pd', action='store_true', dest='bPathDisp',
                 default=False, help='Plot all path')
    p.add_option('--path_clustering', '--pc', action='store_true', dest='bPathClustering',
                 default=False, help='Get all path')

    
    p.add_option('--class', '--c', action='store', type='int', dest='nClass',
                 default=0, help='Store a class number')
    p.add_option('--task', '--t', action='store', type='int', dest='nTask',
                 default=0, help='Store a task number')
    p.add_option('--type_clustering', '--tc', action='store', dest='typeClustering',
                 default='time', help='Type of clustering algorithm(default=time-based rbf)')
    p.add_option('--data_gen', '--gen', action='store_true', dest='bDataGen',
                 default=False, help='Only data generation')
    p.add_option('--delete', '--del', action='store_true', dest='bDelete',
                 default=False, help='Delete data')
    

    p.add_option('--abnormal', '--an', action='store_true', dest='bAbnormal',
                 default=False, help='Renew pickle files.')
    p.add_option('--simulated_abnormal', '--sim_an', action='store_true', dest='bSimAbnormal',
                 default=False, help='.')
    p.add_option('--roc_human', '--rh', action='store_true', dest='bRocHuman',
                 default=False, help='Plot by a figure of ROC human')
    p.add_option('--roc_online_robot', '--ron', action='store_true', dest='bRocOnlineRobot',
                 default=False, help='Plot by a figure of ROC robot')
    p.add_option('--roc_offline_robot', '--roff', action='store_true', dest='bRocOfflineRobot',
                 default=False, help='Plot by a figure of ROC robot')
    p.add_option('--progress_diff', '--prd', action='store_true', dest='bProgressDiff',
                 default=False, help='Plot progress difference')
    p.add_option('--fftdisp', '--fd', action='store_true', dest='bFftDisp',
                 default=False, help='Plot')
    p.add_option('--use_ml_pkl', '--mp', action='store_true', dest='bUseMLObspickle',
                 default=False, help='Use pre-trained object file')
    opt, args = p.parse_args()


    ## data_path = os.environ['HRLBASEPATH']+'/src/projects/anomaly/test_data/'
    cross_root_path = '/home/dpark/hrl_file_server/dpark_data/anomaly/Humanoids2015/robot'
    ## all_task_names  = ['microwave_black', 'microwave_white', 'lab_cabinet', 'wallsw', 'switch_device', \
    ##                    'switch_outlet', 'case', 'lock_wipes', 'lock_huggies', 'toaster_white', 'glass_case']
    all_task_names  = ['microwave_black', 'microwave_white', 'lab_cabinet', 'wallsw', 'switch_device', \
                       'switch_outlet', 'lock_wipes', 'lock_huggies', 'toaster_white', 'glass_case']
    ## all_task_names  = ['microwave_white']

    
    class_num = int(opt.nClass)
    task  = int(opt.nTask)

    if class_num == 0:
        class_name = 'door'
        task_names = ['microwave_black', 'microwave_white', 'lab_cabinet']
        f_zero_size = [8, 5, 10]
        f_thres     = [1.0, 1.7, 3.0]
        audio_thres = [1.0, 1.0, 1.0]
        cov_mult = [[10.0, 10.0, 10.0, 10.0],[10.0, 10.0, 10.0, 10.0],[10.0, 10.0, 10.0, 10.0]]
        nState_l    = [20, 20, 10]
    elif class_num == 1: 
        class_name = 'switch'
        task_names = ['wallsw', 'switch_device', 'switch_outlet']
        f_zero_size = [5, 10, 7]
        f_thres     = [0.7, 0.8, 1.0]
        audio_thres = [1.0, 0.7, 0.0015]
        cov_mult = [[10.0, 10.0, 10.0, 10.0],[50.0, 50.0, 50.0, 50.0],[10.0, 10.0, 10.0, 10.0]]
        nState_l    = [10, 20, 20]
    elif class_num == 2:        
        class_name = 'lock'
        task_names = ['case', 'lock_wipes', 'lock_huggies']
        f_zero_size = [5, 5, 5]
        f_thres     = [0.7, 1.0, 1.35]
        audio_thres = [1.0, 1.0, 1.0]
        cov_mult = [[10.0, 10.0, 10.0, 10.0],[10.0, 10.0, 10.0, 10.0],[10.0, 10.0, 10.0, 10.0]]
        nState_l    = [20, 10, 20]
    elif class_num == 3:        
        class_name = 'complex'
        task_names = ['toaster_white', 'glass_case']
        f_zero_size = [5, 3, 8]
        f_thres     = [0.8, 1.5, 1.35]
        audio_thres = [1., 1.0, 1.0]
        cov_mult    = [[10.0, 10.0, 10.0, 10.0],[20.0, 20.0, 20.0, 20.0],[10.0, 10.0, 10.0, 10.0]]
        nState_l    = [20, 20, 20] #glass 10?
    elif class_num == 4:        
        class_name = 'button'
        task_names = ['joystick', 'keyboard']
        f_zero_size = [5, 5, 8]
        f_thres     = [1.35, 1.35, 1.35]
        audio_thres = [1.0, 1.0, 1.0]
        cov_mult    = [[10.0, 10.0, 10.0, 10.0],[10.0, 10.0, 10.0, 10.0],[10.0, 10.0, 10.0, 10.0]]
        nState_l    = [20, 20, 20]
    else:
        print "Please specify right task."
        sys.exit()

    scale = 10.0       
    freq  = 43.0 #Hz
    
    # Load data
    pkl_file  = os.path.join(cross_root_path,task_names[task]+"_data.pkl")    
    data_path = os.environ['HRLBASEPATH']+'/src/projects/anomaly/test_data/robot_20150213/'+class_name+'/'
      
    #---------------------------------------------------------------------------           
    # Run evaluation
    #---------------------------------------------------------------------------           
    if opt.bRocOnlineSimDimCheck: 
        
        print "ROC Offline Robot with simulated anomalies"
        test_title      = 'online_dim_comp'
        cross_data_path = os.path.join(cross_root_path, 'multi_sim_'+task_names[task], test_title)
        nState          = nState_l[task]
        threshold_mult  = -1.0*(np.logspace(0.1, 2.0, 30, endpoint=True) - 5.0 )
        attr            = 'id'
        onoff_type      = 'online'
        check_methods   = ['progress']
        check_dims      = [0,1,2]
        an_type         = 'both'
        force_an        = ['inelastic', 'inelastic_continue', 'elastic', 'elastic_continue']
        sound_an        = ['rndsharp', 'rnddull'] 
        disp            = 'None'

        true_aXData1, true_aXData2, true_chunks, false_aXData1, false_aXData2, false_chunks, nDataSet \
          = dm.loadData(pkl_file, data_path, task_names[task], f_zero_size[task], f_thres[task], \
                        audio_thres[task], cross_data_path, an_type, force_an, sound_an)

                        
        if opt.bAllPlot is not True:
            fig_roc(test_title, cross_data_path, nDataSet, onoff_type, check_methods, check_dims, \
                    task_names[task], nState, threshold_mult, \
                    opr='robot', attr='id', bPlot=opt.bPlot, cov_mult=cov_mult[task], renew=False, \
                    disp=disp, rm_run=opt.bRemoveRunning, sim=True)
        else:
            fig_roc_all(cross_root_path, all_task_names, test_title, nState, threshold_mult, check_methods, \
                        check_dims, an_type, force_an, sound_an, sim=True)

                            
            
    #---------------------------------------------------------------------------           
    elif opt.bRocOnlineSimMethodCheck:
        
        print "ROC Online Robot with simulated anomalies"
        test_title      = 'online_method_comp'
        cross_data_path = os.path.join(cross_root_path, 'multi_sim_'+task_names[task], test_title)
        nState          = nState_l[task]
        threshold_mult  = -1.0*(np.logspace(-1.0, 2.5, 30, endpoint=True) -2.0)
        attr            = 'id'
        onoff_type      = 'online'
        check_methods   = ['change', 'global', 'globalChange', 'progress']
        check_dims      = [2]
        an_type         = 'both'
        force_an        = ['normal', 'inelastic', 'inelastic_continue', 'elastic', 'elastic_continue']
        sound_an        = ['normal', 'rndsharp', 'rnddull'] 
        disp            = 'None'

        # temp
        ## threshold_mult  = [2.0]
        ## check_methods   = ['globalChange']
        ## disp            = 'test'
            
        true_aXData1, true_aXData2, true_chunks, false_aXData1, false_aXData2, false_chunks, nDataSet \
          = dm.loadData(pkl_file, data_path, task_names[task], f_zero_size[task], f_thres[task], \
                        audio_thres[task], cross_data_path, an_type, force_an, sound_an)

        if opt.bAllPlot is not True:
            fig_roc(test_title, cross_data_path, nDataSet, onoff_type, check_methods, check_dims, \
                    task_names[task], nState, threshold_mult, \
                    opr='robot', attr='id', bPlot=opt.bPlot, cov_mult=cov_mult[task], renew=False, \
                    disp=disp, rm_run=opt.bRemoveRunning, sim=True)
        else:
            fig_roc_all(cross_root_path, all_task_names, test_title, nState, threshold_mult, check_methods, \
                        check_dims, an_type, force_an, sound_an, sim=True)

                        
    #---------------------------------------------------------------------------           
    elif opt.bRocOnlineDimCheck:
        
        print "ROC Online Robot with real anomalies"
        if opt.typeClustering == 'time': test_title      = 'online_dim_comp'
        else: test_title      = 'online_dim_comp_state'
        cross_data_path = os.path.join(cross_root_path, 'multi_'+task_names[task], test_title)
        nState          = nState_l[task]
        threshold_mult  = -1.0*(np.logspace(-1.0, 2.5, 30, endpoint=True) -2.0)
        attr            = 'id'
        onoff_type      = 'online'
        check_methods   = ['progress']
        check_dims      = [0,1,2]
        disp            = 'None'

        ## true_aXData1, true_aXData2, true_chunks, false_aXData1, false_aXData2, false_chunks, nDataSet \
        ##   = dm.loadData(pkl_file, data_path, task_names[task], f_zero_size[task], f_thres[task], \
        ##                 audio_thres[task], cross_data_path, nDataSet=-1)
        nDataSet = dm.kFoldLoadData(pkl_file, data_path, task_names[task], f_zero_size[task], f_thres[task], \
                                    audio_thres[task], cross_data_path, kFold=3)

        if opt.bAllPlot is not True:
            fig_roc(test_title, cross_data_path, nDataSet, onoff_type, check_methods, check_dims, \
                    task_names[task], nState, threshold_mult, \
                    opr='robot', attr='id', bPlot=opt.bPlot, cov_mult=cov_mult[task], renew=False, \
                    cluster_type=opt.typeClustering, \
                    disp=disp, rm_run=opt.bRemoveRunning)
        else:
            fig_roc_all(cross_root_path, all_task_names, test_title, nState, threshold_mult, check_methods, \
                        check_dims)

                        
    #---------------------------------------------------------------------------           
    elif opt.bRocOnlineMethodCheck:
        
        print "ROC Online Robot with real anomalies"
        if opt.typeClustering == 'time': test_title      = 'online_method_comp'
        else: test_title      = 'online_method_comp_state'
        
        cross_data_path = os.path.join(cross_root_path, 'multi_'+task_names[task], test_title)
        nState          = nState_l[task]
        threshold_mult  = -1.0*(np.logspace(-1.0, 2.5, 30, endpoint=True) -2.0)
        attr            = 'id'
        onoff_type      = 'online'
        check_methods   = ['change', 'global', 'progress']
        ## check_methods   = ['change', 'global', 'globalChange', 'progress']
        check_dims      = [2]
        disp            = 'None'

        
        ## true_aXData1, true_aXData2, true_chunks, false_aXData1, false_aXData2, false_chunks, nDataSet \
        ##   = dm.loadData(pkl_file, data_path, task_names[task], f_zero_size[task], f_thres[task], \
        ##                 audio_thres[task], cross_data_path)

        if opt.bAllPlot is not True:
            nDataSet = dm.kFoldLoadData(pkl_file, data_path, task_names[task], f_zero_size[task], f_thres[task],\
                                        audio_thres[task], cross_data_path, kFold=3)
            fig_roc(test_title, cross_data_path, nDataSet, onoff_type, check_methods, check_dims, \
                    task_names[task], nState, threshold_mult, \
                    opr='robot', attr='id', bPlot=opt.bPlot, cov_mult=cov_mult[task], renew=False, \
                    cluster_type=opt.typeClustering, \
                    disp=disp, rm_run=opt.bRemoveRunning)
        else:
            fig_roc_all(cross_root_path, all_task_names, test_title, nState, threshold_mult, check_methods, \
                        check_dims)
                            

    #---------------------------------------------------------------------------           
    elif opt.bRocOfflineMethodCheck:
        
        print "ROC Online Robot with real anomalies"
        test_title      = 'offline_method_comp'
        cross_data_path = os.path.join(cross_root_path, 'multi_'+task_names[task], test_title)
        nState          = nState_l[task]
        threshold_mult  = -1.0*(np.logspace(-1.0, 2.5, 30, endpoint=True) -2.0)
        attr            = 'id'
        onoff_type      = 'offline'
        check_methods   = ['global', 'progress']
        check_dims      = [2]
        disp            = 'None'

        true_aXData1, true_aXData2, true_chunks, false_aXData1, false_aXData2, false_chunks, nDataSet \
          = dm.loadData(pkl_file, data_path, task_names[task], f_zero_size[task], f_thres[task], \
                        audio_thres[task], cross_data_path)

        if opt.bAllPlot is not True:
            fig_roc(test_title, cross_data_path, nDataSet, onoff_type, check_methods, check_dims, \
                    task_names[task], nState, threshold_mult, \
                    opr='robot', attr='id', bPlot=opt.bPlot, cov_mult=cov_mult[task], renew=False, \
                    disp=disp, rm_run=opt.bRemoveRunning)
        else:
            fig_roc_all(cross_root_path, all_task_names, test_title, nState, threshold_mult, check_methods, \
                        check_dims)


    #---------------------------------------------------------------------------           
    elif opt.bRocOfflineDimCheck:
        
        print "ROC Online Robot with real anomalies"
        test_title      = 'offline_dim_comp'
        cross_data_path = os.path.join(cross_root_path, 'multi_'+task_names[task], test_title)
        nState          = nState_l[task]
        threshold_mult  = -1.0*(np.logspace(-1.0, 2.5, 30, endpoint=True) -2.0)
        attr            = 'id'
        onoff_type      = 'offline'
        check_methods   = ['progress']
        check_dims      = [0,1,2]
        disp            = 'None'

        true_aXData1, true_aXData2, true_chunks, false_aXData1, false_aXData2, false_chunks, nDataSet \
          = dm.loadData(pkl_file, data_path, task_names[task], f_zero_size[task], f_thres[task], \
                        audio_thres[task], cross_data_path, nDataSet=-1)

        if opt.bAllPlot is not True:
            fig_roc(test_title, cross_data_path, nDataSet, onoff_type, check_methods, check_dims, \
                    task_names[task], nState, threshold_mult, \
                    opr='robot', attr='id', bPlot=opt.bPlot, cov_mult=cov_mult[task], renew=False, \
                    disp=disp, rm_run=opt.bRemoveRunning)
        else:
            fig_roc_all(cross_root_path, all_task_names, test_title, nState, threshold_mult, check_methods, \
                        check_dims)

                        
    #---------------------------------------------------------------------------           
    elif opt.bOnlineMethodCheck:
        
        print "Evaluation for Online Robot with real anomalies and automatic threshold decision"
        test_title      = 'online_method_check'
        cross_data_path = os.path.join(cross_root_path, 'multi_'+task_names[task], test_title)
        nState          = nState_l[task]
        attr            = 'id'
        onoff_type      = 'online'
        check_methods   = ['change', 'global', 'globalChange', 'progress']
        check_dims      = [2]
        disp            = 'None'
        rFold           = 0.75 # ratio of training dataset in true dataset
        nDataSet        = -1 #number of all true data

        true_aXData1, true_aXData2, true_chunks, false_aXData1, false_aXData2, false_chunks, nDataSet \
          = dm.loadData(pkl_file, data_path, task_names[task], f_zero_size[task], f_thres[task], \
                        audio_thres[task], cross_data_path, rFold=rFold, nDataSet=nDataSet)

        if opt.bAllPlot is not True:
            fig_eval(test_title, cross_data_path, nDataSet, onoff_type, check_methods, check_dims, \
                     task_names[task], nState, \
                     opr='robot', attr='id', bPlot=opt.bPlot, cov_mult=cov_mult[task], renew=opt.bRenew, \
                     disp=disp, rm_run=opt.bRemoveRunning)
        else:
            fig_eval_all(cross_root_path, all_task_names, test_title, nState, check_methods, \
                         check_dims, nDataSet, renew=opt.bRenew)


    #---------------------------------------------------------------------------
    elif opt.bOnlineSimMethodParamCheck:

        # force3 = 2dim + all with large distribution of sim anomaly
        # sound  = 2dim + all
        
        print "ROC Online Robot with simulated anomalies"
        ## test_title      = 'online_method_param_check_sound'        
        ## check_dims      = [2]
        ## force_an        = ['normal']        
        ## sound_an        = ['rndsharp', 'rnddull'] 

        test_title      = 'online_method_param_check_force3'   # used for figure!!!     
        ## test_title      = 'online_method_param_check_force4'  
        check_dims      = [2]            
        force_an        = ['inelastic', 'inelastic_continue', 'elastic', 'elastic_continue']
        sound_an        = ['normal'] 
            
        cross_data_path = os.path.join(cross_root_path, 'multi_sim_'+task_names[task], test_title)
        nState          = nState_l[task]
        attr            = 'id'
        onoff_type      = 'online'
        check_methods   = ['change', 'global', 'globalChange', 'progress']
        an_type         = 'both'
        
        disp            = 'None'
        rFold           = 0.75 # ratio of training dataset in true dataset #used for figure
        ## rFold           = 0.5 # ratio of training dataset in true dataset #used for figure
        nDataSet        = -1

        if opt.bDelete:
            os.system('rm '+os.path.join(cross_root_path, test_title)+'*' )
            print 'rm '+os.path.join(cross_root_path, test_title)+'*' 
        
        true_aXData1, true_aXData2, true_chunks, false_aXData1, false_aXData2, false_chunks, nDataSet \
          = dm.loadData(pkl_file, data_path, task_names[task], f_zero_size[task], f_thres[task], \
                        audio_thres[task], cross_data_path, an_type, force_an, sound_an, 
                        rFold=rFold, nDataSet=nDataSet, delete=opt.bDelete)
        if opt.bDataGen: 
            sys.exit()


        if opt.bAllPlot is not True:
            fig_eval(test_title, cross_data_path, nDataSet, onoff_type, check_methods, check_dims, \
                     task_names[task], nState, \
                     opr='robot', attr='id', bPlot=opt.bPlot, cov_mult=cov_mult[task], renew=opt.bRenew, \
                     disp=disp, rm_run=opt.bRemoveRunning, sim=True, detect_break=True)
        else:
            fig_eval_all(cross_root_path, all_task_names, test_title, nState, check_methods, \
                         check_dims, nDataSet, sim=True, renew=True)

                        
    #---------------------------------------------------------------------------
    elif opt.bOnePlot:

        print "Visualization of each sequence"
        true_aXData1, true_aXData2, true_chunks, false_aXData1, false_aXData2, false_chunks, nDataSet \
          = dm.loadData(pkl_file, data_path, task_names[task], f_zero_size[task], f_thres[task], \
                        audio_thres[task])
        
        ## true_aXData1_scaled, min_c1, max_c1 = dm.scaling(true_aXData1, scale=scale)
        ## true_aXData2_scaled, min_c2, max_c2 = dm.scaling(true_aXData2, scale=scale)    

        if opt.bAbnormal or opt.bSimAbnormal:
            for idx in xrange(len(false_aXData1)):
                # min max scaling
                ## false_aXData1_scaled, _, _ = dm.scaling(false_aXData1, min_c1, max_c1, scale=scale)
                ## false_aXData2_scaled, _, _ = dm.scaling(false_aXData2, min_c2, max_c2, scale=scale)

                plot_one(true_aXData1, true_aXData2, false_aXData1, false_aXData2, data_idx=idx, freq=freq)

        else:
            for idx in xrange(len(true_aXData1)):
                plot_one(true_aXData1, true_aXData2, data_idx=idx, freq=freq)            

            
    #---------------------------------------------------------------------------
    elif opt.bAllPlot:

        print "Visualization of all sequence"
        true_aXData1, true_aXData2, true_chunks, false_aXData1, false_aXData2, false_chunks, nDataSet \
          = dm.loadData(pkl_file, data_path, task_names[task], f_zero_size[task], f_thres[task], \
                        audio_thres[task])
        
        true_aXData1_scaled, min_c1, max_c1 = dm.scaling(true_aXData1, scale=scale)
        true_aXData2_scaled, min_c2, max_c2 = dm.scaling(true_aXData2, scale=scale)    

        if opt.bAbnormal or opt.bSimAbnormal:
            
            # min max scaling
            false_aXData1_scaled, _, _ = dm.scaling(false_aXData1, min_c1, max_c1, scale=scale)
            false_aXData2_scaled, _, _ = dm.scaling(false_aXData2, min_c2, max_c2, scale=scale)
                        
            ## plot_all(true_aXData1_scaled, true_aXData2_scaled, false_aXData1_scaled, false_aXData2_scaled)
            ## plot_all(true_aXData1, true_aXData2, false_aXData1, false_aXData2)
            plot_all(true_aXData1, true_aXData2, false_aXData1, false_aXData2, distribution=True)
            
        else:
            ## plot_all(true_aXData1_scaled, true_aXData2_scaled)            
            plot_all(true_aXData1, true_aXData2)            

        ## print min_c1, max_c1, np.min(aXData1_scaled), np.max(aXData1_scaled)
        ## print min_c2, max_c2, np.min(aXData2_scaled), np.max(aXData2_scaled)


    #---------------------------------------------------------------------------   
    elif opt.bPathDisp:
        # ICRA figure 
        # run > python test_multi_modality.py --pd --c 0 --t 1
        
        print "Hidden-state path Visualization of each sequence"
        true_aXData1, true_aXData2, true_chunks, false_aXData1, false_aXData2, false_chunks, nDataSet \
          = dm.loadData(pkl_file, data_path, task_names[task], f_zero_size[task], f_thres[task], \
                        audio_thres[task])
        
        nState   = nState_l[task]
        trans_type= "left_right"
        check_dim = 2
        if check_dim == 0 or check_dim == 1: nEmissionDim=1
        else: nEmissionDim=2

        aXData1_scaled, min_c1, max_c1 = dm.scaling(true_aXData1)
        aXData2_scaled, min_c2, max_c2 = dm.scaling(true_aXData2)    
        true_labels = [True]*len(true_aXData1)

        true_dataSet = dm.create_mvpa_dataset(aXData1_scaled, aXData2_scaled, true_chunks, true_labels)
            
        x_train1  = true_dataSet.samples[:,0,:]
        x_train2  = true_dataSet.samples[:,1,:]

        # Learning
        lhm = learning_hmm_multi(nState=nState, trans_type=trans_type, nEmissionDim=nEmissionDim)

        if check_dim == 0: lhm.fit(x_train1, cov_mult=[cov_mult[task][0]]*4)
        elif check_dim == 1: lhm.fit(x_train2, cov_mult=[cov_mult[task][3]]*4)
        else: lhm.fit(x_train1, x_train2, cov_mult=cov_mult[task])

        x_test1 = x_train1 #[:1]
        x_test2 = x_train2 #[:1]
        lhm.path_disp(x_test1, x_test2, scale1=[min_c1, max_c1, scale], \
                                scale2=[min_c2, max_c2, scale])


    #---------------------------------------------------------------------------   
    elif opt.bPathClustering:
            
        print "Hidden-state path Visualization of each sequence"
        true_aXData1, true_aXData2, true_chunks, false_aXData1, false_aXData2, false_chunks, nDataSet \
          = dm.loadData(pkl_file, data_path, task_names[task], f_zero_size[task], f_thres[task], \
                        audio_thres[task])
        
        nState   = nState_l[task]
        trans_type= "left_right"
        check_dim = 2
        if check_dim == 0 or check_dim == 1: nEmissionDim=1
        else: nEmissionDim=2

        aXData1_scaled, min_c1, max_c1 = dm.scaling(true_aXData1)
        aXData2_scaled, min_c2, max_c2 = dm.scaling(true_aXData2)    
        true_labels = [True]*len(true_aXData1)

        true_dataSet = dm.create_mvpa_dataset(aXData1_scaled, aXData2_scaled, true_chunks, true_labels)
            
        x_train1  = true_dataSet.samples[:,0,:]
        x_train2  = true_dataSet.samples[:,1,:]

        # Learning
        cluster_type='time'
        lhm = learning_hmm_multi(nState=nState, trans_type=trans_type, nEmissionDim=nEmissionDim,\
                                 cluster_type=cluster_type)


        res_file = 'clustering.pkl'
        if os.path.isfile(res_file) is False: 
        
            if check_dim == 0: lhm.fit(x_train1, cov_mult=[cov_mult[task][0]]*4)
            elif check_dim == 1: lhm.fit(x_train2, cov_mult=[cov_mult[task][3]]*4)
            else: lhm.fit(x_train1, x_train2, cov_mult=cov_mult[task])

        x_test1 = x_train1
        x_test2 = x_train2
        lhm.path_cluster(x_test1, x_test2, res_file, scale1=[min_c1, max_c1, scale], \
                         scale2=[min_c2, max_c2, scale])
                                
    #---------------------------------------------------------------------------           
    ## elif opt.bRocOfflineSimMethodCheck:
        
    ##     print "ROC Online Robot with simulated anomalies"
    ##     cross_data_path = os.path.join(cross_root_path, 'multi_sim_'+task_names[task])
    ##     nState          = nState_l[task]
    ##     threshold_mult  = np.logspace(-1.0, 1.5, 20, endpoint=True) # np.arange(0.0, 30.001, 2.0) #
    ##     attr            = 'id'
    ##     onoff_type      = 'online'
    ##     check_methods   = ['global', 'progress']
    ##     check_dims      = [2]
    ##     test_title      = 'offline_method_comp'

    ##     fig_roc_sim(test_title, cross_data_path, nDataSet, onoff_type, check_methods, check_dims, \
    ##                 task_names[task], nState, threshold_mult, \
    ##                 opr='robot', attr='id', bPlot=opt.bPlot, cov_mult=cov_mult[task], renew=False)

                    
    ## #---------------------------------------------------------------------------           
    ## elif opt.bRocOnlineRobot:

    ##     cross_data_path = os.path.join(cross_root_path, 'multi_'+task_names[task])
    ##     nState          = nState_l[task]
    ##     threshold_mult  = np.arange(0.0, 4.2, 0.1)    
    ##     attr            = 'id'

    ##     fig_roc(cross_data_path, aXData1, aXData2, chunks, labels, task_names[task], nState, threshold_mult, \
    ##             opr='robot', attr='id', bPlot=opt.bPlot, cov_mult=cov_mult[task])

    ##     if opt.bAllPlot:
    ##         if task ==1:
    ##             ## prefixes = ['microwave', 'microwave_black', 'microwave_white']
    ##             prefixes = ['microwave', 'microwave_black']
    ##         else:
    ##             prefixes = ['microwave', 'microwave_black']
                
    ##         cross_data_path = '/home/dpark/hrl_file_server/dpark_data/anomaly/Humanoids2015/robot'                
    ##         fig_roc_all(cross_data_path, nState, threshold_mult, prefixes, opr='robot', attr='id')
            
            
    #---------------------------------------------------------------------------           
    elif opt.bRocOfflineRobot:
        
        print "ROC Offline Robot"
        cross_data_path = os.path.join(cross_root_path, 'multi_'+task_names[task])
        nState          = nState_l[task]
        threshold_mult  = np.arange(0.0, 24.2, 0.3)    
        attr            = 'id'

        fig_roc_offline(cross_data_path, \
                        true_aXData1, true_aXData2, true_chunks, \
                        false_aXData1, false_aXData2, false_chunks, \
                        task_names[task], nState, threshold_mult, \
                        opr='robot', attr='id', bPlot=opt.bPlot)

        if opt.bAllPlot:
            if task ==1:
                ## prefixes = ['microwave', 'microwave_black', 'microwave_white']
                prefixes = ['microwave', 'microwave_black']
            else:
                prefixes = ['microwave', 'microwave_black']
                
            cross_data_path = '/home/dpark/hrl_file_server/dpark_data/anomaly/Humanoids2015/robot'                
            fig_roc_all(cross_data_path, nState, threshold_mult, prefixes, opr='robot', attr='id')
            


        
    #---------------------------------------------------------------------------   
    elif opt.bFftDisp:
        d = dm.load_data(data_path, task_names[task], normal_only=False)
        
        audio_time_list = d['audio_time']
        audio_data_list = d['audio_data']

        plot_audio(audio_time_list[0], audio_data_list[0])
        
            
    #---------------------------------------------------------------------------   
    elif opt.bAnimation:

        print "Evaluation for Online Robot with real anomalies and automatic threshold decision"
        test_title      = 'online_animation'
        cross_data_path = os.path.join(cross_root_path, 'multi_'+task_names[task], test_title)
        nState          = nState_l[task]
        attr            = 'id'
        onoff_type      = 'online'
        check_methods   = ['progress']
        check_dims      = [2]
        disp            = 'None'
        rFold           = 0.75 # ratio of training dataset in true dataset
        nDataSet        = 1

        ## nMaxStep = 36 # total step of data. It should be automatically assigned...
        true_aXData1, true_aXData2, true_chunks, false_aXData1, false_aXData2, false_chunks, nDataSet \
          = dm.loadData(pkl_file, data_path, task_names[task], f_zero_size[task], f_thres[task], \
                        audio_thres[task], cross_data_path, rFold=rFold, nDataSet=nDataSet)

        animation(test_title, cross_data_path, nDataSet, onoff_type, check_methods, check_dims, \
                     task_names[task], nState, \
                     opr='robot', attr='id', cov_mult=cov_mult[task], true_data=True)
                        
        ## c0t1 - true=4, false=0
        ## c0t2 - true=1, false=0
        ## c1t2 - true=2, false=0
                

    #---------------------------------------------------------------------------   
    elif opt.bProgressDiff:

        nState   = nState_l[task]
        trans_type= "left_right"
        check_dim = 2
        if check_dim == 0 or check_dim == 1: nEmissionDim=1
        else: nEmissionDim=2

        # Get train/test dataset
        aXData1_scaled, min_c1, max_c1 = dm.scaling(true_aXData1)
        aXData2_scaled, min_c2, max_c2 = dm.scaling(true_aXData2)    
        true_labels = [True]*len(true_aXData1)

        state_diff = None
            
        for i in xrange(len(true_labels)):
                
            true_dataSet = dm.create_mvpa_dataset(aXData1_scaled, aXData2_scaled, true_chunks, true_labels)
            test_dataSet  = true_dataSet[i:i+1]
            train_ids = [val for val in true_dataSet.sa.id if val not in test_dataSet[0].sa.id] 
            train_ids = Dataset.get_samples_by_attr(true_dataSet, 'id', train_ids)
            train_dataSet = true_dataSet[train_ids]

            x_train1 = train_dataSet.samples[:,0,:]
            x_train2 = train_dataSet.samples[:,1,:]

            # Learning
            lhm = learning_hmm_multi(nState=nState, trans_type=trans_type, nEmissionDim=nEmissionDim)

            if check_dim == 0: lhm.fit(x_train1, cov_mult=[cov_mult[task][0]]*4)
            elif check_dim == 1: lhm.fit(x_train2, cov_mult=[cov_mult[task][3]]*4)
            else: lhm.fit(x_train1, x_train2, cov_mult=cov_mult[task])

            x_test1  = test_dataSet.samples[:,0,:]
            x_test2  = test_dataSet.samples[:,1,:]

            off_progress, online_progress = lhm.progress_analysis(x_test1, x_test2, 
                                                                  scale1=[min_c1, max_c1, scale], 
                                                                  scale2=[min_c2, max_c2, scale])
            if state_diff is None:
                state_diff = off_progress-online_progress
            else:
                state_diff = np.vstack([state_diff, off_progress-online_progress])


        mu  = np.mean(state_diff,axis=0)
        sig = np.std(state_diff,axis=0)
        x   = np.arange(0., float(len(mu))) * (1./freq)

        matplotlib.rcParams['pdf.fonttype'] = 42
        matplotlib.rcParams['ps.fonttype'] = 42
        
        fig = plt.figure()
        plt.rc('text', usetex=True)
        
        ax1 = plt.subplot(111)
        ax1.plot(x, mu, '-g')
        ax1.fill_between(x, mu-sig, mu+sig, facecolor='green', edgecolor='1.0',
                         alpha=0.5, interpolate=True)
        
        ax1.set_ylabel('Estimation Error', fontsize=18)
        ax1.set_xlabel('Time [sec]', fontsize=18)

        mu_line = ax1.plot([], [], color='green', linewidth=2, 
                             label=r'$\mu$') #fake for legend
        bnd_line = ax1.plot([], [], color='green', alpha=0.5, linewidth=10, 
                             label=r'$\mu+\sigma$') #fake for legend
        
        ax1.legend(loc=1,prop={'size':18})       
        plt.show()

        fig.savefig('test.pdf')
        fig.savefig('test.png')
        
        
    #---------------------------------------------------------------------------           
    else:

        nState   = nState_l[task]
        trans_type= "left_right"
        check_dim = 2
        if check_dim == 0 or check_dim == 1: nEmissionDim=1
        else: nEmissionDim=2
        
        if opt.bAbnormal:
            test_title      = 'online_method_comp'
            cross_data_path = os.path.join(cross_root_path, 'multi_sim_'+task_names[task], test_title)
            false_data_flag = True
            true_aXData1, true_aXData2, true_chunks, false_aXData1, false_aXData2, false_chunks, nDataSet \
              = dm.loadData(pkl_file, data_path, task_names[task], f_zero_size[task], f_thres[task], 
                         audio_thres[task], cross_data_path)            
        else:
            false_data_flag = False       
            true_aXData1, true_aXData2, true_chunks, false_aXData1, false_aXData2, false_chunks, nDataSet \
              = dm.loadData(pkl_file, data_path, task_names[task], f_zero_size[task], f_thres[task], 
                         audio_thres[task])
                
        # Get train/test dataset
        aXData1_scaled, min_c1, max_c1 = dm.scaling(true_aXData1)
        aXData2_scaled, min_c2, max_c2 = dm.scaling(true_aXData2)    
        true_labels = [True]*len(true_aXData1)

        true_dataSet = dm.create_mvpa_dataset(aXData1_scaled, aXData2_scaled, true_chunks, true_labels)
        test_dataSet  = true_dataSet[0:10]
        train_ids = [val for val in true_dataSet.sa.id if val not in test_dataSet[0].sa.id] 
        train_ids = Dataset.get_samples_by_attr(true_dataSet, 'id', train_ids)
        train_dataSet = true_dataSet[train_ids]

        x_train1 = train_dataSet.samples[:,0,:]
        x_train2 = train_dataSet.samples[:,1,:]

        # generate simulated data!!
        false_aXData1_scaled, _, _ = dm.scaling(false_aXData1, min_c1, max_c1, scale=scale)
        false_aXData2_scaled, _, _ = dm.scaling(false_aXData2, min_c2, max_c2, scale=scale)    
        false_labels = [False]*len(false_aXData1)
        false_dataSet = dm.create_mvpa_dataset(false_aXData1_scaled, false_aXData2_scaled, \
                                               false_chunks, false_labels)

        # If you want normal likelihood, class 0, data 1
        # testData 0
        # false data 0 (make it false)

        # ICRA figure generation
        # 1) python test_multi_modality.py --c 0 --t 1
        # 2) python test_multi_modality.py --c 0 --t 1 --an
        
        if false_data_flag:
            test_dataSet    = false_dataSet
                                                               
        for K in range(len(test_dataSet)):
            print "Test number : ", K
            
            if false_data_flag:
                x_test1 = np.array([test_dataSet.samples[K:K+1,0][0]])
                x_test2 = np.array([test_dataSet.samples[K:K+1,1][0]])
            else:
                x_test1  = test_dataSet.samples[:,0,:]
                x_test2  = test_dataSet.samples[:,1,:]
            
            # Learning
            lhm = learning_hmm_multi(nState=nState, trans_type=trans_type, nEmissionDim=nEmissionDim, \
                                     cluster_type=opt.typeClustering)
            
            if check_dim == 0: lhm.fit(x_train1, cov_mult=[cov_mult[task][0]]*4)
            elif check_dim == 1: lhm.fit(x_train2, cov_mult=[cov_mult[task][3]]*4)
            else: lhm.fit(x_train1, x_train2, cov_mult=cov_mult[task], ml_pkl='likelihood.pkl', \
                          use_pkl=opt.bUseMLObspickle)


            ## # TEST
            ## ------------------------------------------------------------------
            ## nCurrentStep = 27
            ## ## X_test1 = aXData1_scaled[0:1,:nCurrentStep]
            ## ## X_test2 = aXData2_scaled[0:1,:nCurrentStep]
            ## X_test1 = aXData1_scaled[0:1]
            ## X_test2 = aXData2_scaled[0:1]
            
            ## #
            ## X_test2[0,nCurrentStep-3] = 10.7
            ## X_test2[0,nCurrentStep-2] = 12.7
            ## X_test2[0,nCurrentStep-1] = 11.7

            ## ------------------------------------------------------------------
            ## aXData1_scaled, _, _ = dm.scaling(false_aXData1, min_c1, max_c1)
            ## aXData2_scaled, _, _ = dm.scaling(false_aXData2, min_c2, max_c2)    

            ## idx = 0
            ## print "Chunk name: ", false_chunks[idx]
            ## X1 = np.array([aXData1_scaled[idx]])
            ## X2 = np.array([aXData2_scaled[idx]])


            lhm.likelihood_disp(x_test1, x_test2, 3.0, scale1=[min_c1, max_c1, scale], \
                                scale2=[min_c2, max_c2, scale])
            print "-------------------------------------------------------------------"


            ## lhm.data_plot(X_test1, X_test2, color = 'r')

            ## X_test2[0,nCurrentStep-2] = 12.7
            ## X_test2[0,nCurrentStep-1] = 11.7
            ## X_test = lhm.convert_sequence(X_test1[:nCurrentStep], X_test2[:nCurrentStep], emission=False)

            ## fp, err = lhm.anomaly_check(X_test1, X_test2, ths_mult=0.01)
            ## print fp, err
            
            ## ## print lhm.likelihood(X_test), lhm.likelihood_avg
            ## ## mu, cov = self.predict(X_test)

            ## lhm.data_plot(X_test1, X_test2, color = 'b')

    ## #---------------------------------------------------------------------------           
    ## if opt.bRocHuman:
    ##     # not used for a while

    ##     cross_data_path = '/home/dpark/hrl_file_server/dpark_data/anomaly/Humanoids2015/human/multi_'+\
    ##                       task_names[task]
    ##     nState          = 20
    ##     threshold_mult  = np.arange(0.01, 4.0, 0.1)    

    ##     fig_roc(cross_data_path, aXData1, aXData2, chunks, labels, task_names[task], nState, threshold_mult, \
    ##             opr='human', bPlot=opt.bPlot)

    ##     if opt.bAllPlot:
    ##         prefixes = ['microwave', 'microwave_black', 'microwave_white']
    ##         cross_data_path = '/home/dpark/hrl_file_server/dpark_data/anomaly/Humanoids2015/human'
    ##         fig_roc_all(cross_data_path, nState, threshold_mult, prefixes, opr='human', attr='chunks')



## def fig_roc_offline_sim(cross_data_path, \
##                         true_aXData1, true_aXData2, true_chunks, \
##                         false_aXData1, false_aXData2, false_chunks, \
##                         prefix, nState=20, \
##                         threshold_mult = np.arange(0.05, 1.2, 0.05), opr='robot', attr='id', bPlot=False, \
##                         cov_mult=[1.0, 1.0, 1.0, 1.0], renew=False):

##     # For parallel computing
##     strMachine = socket.gethostname()+"_"+str(os.getpid())    
##     trans_type = "left_right"
    
##     # Check the existance of workspace
##     cross_test_path = os.path.join(cross_data_path, str(nState))
##     if os.path.isdir(cross_test_path) == False:
##         os.system('mkdir -p '+cross_test_path)

##     # min max scaling for true data
##     aXData1_scaled, min_c1, max_c1 = dm.scaling(true_aXData1, scale=10.0)
##     aXData2_scaled, min_c2, max_c2 = dm.scaling(true_aXData2, scale=10.0)    
##     labels = [True]*len(true_aXData1)
##     true_dataSet = dm.create_mvpa_dataset(aXData1_scaled, aXData2_scaled, true_chunks, labels)
##     ## print "Scaling data: ", np.shape(true_aXData1), " => ", np.shape(aXData1_scaled)
    
##     # generate simulated data!!
##     aXData1_scaled, _, _ = dm.scaling(false_aXData1, min_c1, max_c1, scale=10.0)
##     aXData2_scaled, _, _ = dm.scaling(false_aXData2, min_c2, max_c2, scale=10.0)    
##     labels = [False]*len(false_aXData1)
##     false_dataSet = dm.create_mvpa_dataset(aXData1_scaled, aXData2_scaled, false_chunks, labels)

##     # K random training-test set
##     K = len(true_aXData1)/4 # the number of test data
##     M = 30
##     splits = []
##     for i in xrange(M):
##     ## for i in xrange(len(true_aXData1)):
##         print "(",K,",",K,") pairs in ", M, "iterations"
        
##         if os.path.isfile(os.path.join(cross_data_path,"train_dataSet_"+str(i))) is False:

##             ## test_dataSet = true_dataSet[i]
##             ## train_ids = [val for val in true_dataSet.sa.id if val not in test_dataSet.sa.id] 
##             ## train_ids = Dataset.get_samples_by_attr(true_dataSet, 'id', train_ids)
##             ## train_dataSet = true_dataSet[train_ids]
##             ## test_false_dataSet = false_dataSet[K]
            
##             test_dataSet  = Dataset.random_samples(true_dataSet, K)
##             train_ids = [val for val in true_dataSet.sa.id if val not in test_dataSet.sa.id] 
##             train_ids = Dataset.get_samples_by_attr(true_dataSet, 'id', train_ids)
##             train_dataSet = true_dataSet[train_ids]
##             test_false_dataSet  = Dataset.random_samples(false_dataSet, K)        

##             Dataset.save(train_dataSet, os.path.join(cross_data_path,"train_dataSet_"+str(i)) )
##             Dataset.save(test_dataSet, os.path.join(cross_data_path,"test_dataSet_"+str(i)) )
##             Dataset.save(test_false_dataSet, os.path.join(cross_data_path,"test_false_dataSet_"+str(i)) )

##         else:
##             try:
##                 train_dataSet = Dataset.from_hdf5( os.path.join(cross_data_path,"train_dataSet_"+str(i)) )
##                 test_dataSet = Dataset.from_hdf5( os.path.join(cross_data_path,"test_dataSet_"+str(i)) )
##                 test_false_dataSet = Dataset.from_hdf5( os.path.join(cross_data_path,"test_false_dataSet_"+str(i)) )
##             except:
##                 print cross_data_path
##                 print "test_dataSet_"+str(i)
            
##         splits.append([train_dataSet, test_dataSet, test_false_dataSet])

            
##     ## Multi dimension
##     for i in xrange(3):        
##         count = 0
##         for ths in threshold_mult:

##             # save file name
##             res_file = prefix+'_roc_'+opr+'_dim_'+str(i)+'_ths_'+str(ths)+'.pkl'
##             res_file = os.path.join(cross_test_path, res_file)

##             mutex_file_part = 'running_dim_'+str(i)+'_ths_'+str(ths)
##             mutex_file_full = mutex_file_part+'_'+strMachine+'.txt'
##             mutex_file      = os.path.join(cross_test_path, mutex_file_full)

##             if os.path.isfile(res_file): 
##                 count += 1            
##                 continue
##             elif hcu.is_file(cross_test_path, mutex_file_part): continue
##             elif os.path.isfile(mutex_file): continue
##             os.system('touch '+mutex_file)

##             print "---------------------------------"
##             print "Total splits: ", len(splits)

##             ## # temp
##             ## fn_ll = []
##             ## tn_ll = []
##             ## fn_err_ll = []
##             ## tn_err_ll = []
##             ## for j, (l_wdata, l_vdata, l_zdata) in enumerate(splits):
##             ##     fn_ll, tn_ll, fn_err_ll, tn_err_ll = anomaly_check_offline(j, l_wdata, l_vdata, nState, \
##             ##                                                            trans_type, ths, l_zdata, \
##             ##                                                            cov_mult=cov_mult, check_dim=i)
##             ##     print np.mean(fn_ll), np.mean(tn_ll)
##             ## sys.exit()
                                  
##             n_jobs = -1
##             r = Parallel(n_jobs=n_jobs)(delayed(anomaly_check_offline)(j, l_wdata, l_vdata, nState, \
##                                                                        trans_type, ths, l_zdata, \
##                                                                        cov_mult=cov_mult, check_dim=i) \
##                                         for j, (l_wdata, l_vdata, l_zdata) in enumerate(splits))
##             fn_ll, tn_ll, fn_err_ll, tn_err_ll = zip(*r)

##             import operator
##             fn_l = reduce(operator.add, fn_ll)
##             tn_l = reduce(operator.add, tn_ll)
##             fn_err_l = reduce(operator.add, fn_err_ll)
##             tn_err_l = reduce(operator.add, tn_err_ll)

##             d = {}
##             d['fn']  = np.mean(fn_l)
##             d['tp']  = 1.0 - np.mean(fn_l)
##             d['tn']  = np.mean(tn_l)
##             d['fp']  = 1.0 - np.mean(tn_l)

##             if fn_err_l == []:         
##                 d['fn_err'] = 0.0
##             else:
##                 d['fn_err'] = np.mean(fn_err_l)

##             if tn_err_l == []:         
##                 d['tn_err'] = 0.0
##             else:
##                 d['tn_err'] = np.mean(tn_err_l)

##             ut.save_pickle(d,res_file)        
##             os.system('rm '+mutex_file)
##             print "-----------------------------------------------"

##         if count == len(threshold_mult):
##             print "#############################################################################"
##             print "All file exist ", count
##             print "#############################################################################"        

        
##     if count == len(threshold_mult) and bPlot:

##         import itertools
##         colors = itertools.cycle(['g', 'm', 'c', 'k'])
##         shapes = itertools.cycle(['x','v', 'o', '+'])
        
##         fig = pp.figure()
        
##         for i in xrange(3):
##             fp_l = []
##             tp_l = []
##             err_l = []
##             for ths in threshold_mult:
##                 res_file   = prefix+'_roc_'+opr+'_dim_'+str(i)+'_'+'ths_'+str(ths)+'.pkl'
##                 res_file   = os.path.join(cross_test_path, res_file)

##                 d = ut.load_pickle(res_file)
##                 tp  = d['tp'] 
##                 fn  = d['fn'] 
##                 fp  = d['fp'] 
##                 tn  = d['tn'] 
##                 fn_err = d['fn_err']         
##                 tn_err = d['tn_err']         

##                 fp_l.append([fp])
##                 tp_l.append([tp])
##                 err_l.append([fn_err])

##             fp_l  = np.array(fp_l)*100.0
##             tp_l  = np.array(tp_l)*100.0

##             idx_list = sorted(range(len(fp_l)), key=lambda k: fp_l[k])
##             sorted_fp_l = [fp_l[j] for j in idx_list]
##             sorted_tp_l = [tp_l[j] for j in idx_list]
            
##             color = colors.next()
##             shape = shapes.next()

##             if i==0: semantic_label='Force only'
##             elif i==1: semantic_label='Sound only'
##             else: semantic_label='Force and sound'
##             pp.plot(sorted_fp_l, sorted_tp_l, '-'+shape+color, label= semantic_label, mec=color, ms=8, mew=2)



##         ## fp_l = fp_l[:,0]
##         ## tp_l = tp_l[:,0]
        
##         ## from scipy.optimize import curve_fit
##         ## def sigma(e, k ,n, offset): return k*((e+offset)**n)
##         ## param, var = curve_fit(sigma, fp_l, tp_l)
##         ## new_fp_l = np.linspace(fp_l.min(), fp_l.max(), 50)        
##         ## pp.plot(new_fp_l, sigma(new_fp_l, *param))

        
##         pp.xlabel('False positive rate (percentage)', fontsize=16)
##         pp.ylabel('True positive rate (percentage)', fontsize=16)    
##         pp.xlim([-1, 100])
##         pp.ylim([-1, 101])
##         pp.legend(loc=4,prop={'size':16})
        
##         pp.show()

##         fig.savefig('test.pdf')
##         fig.savefig('test.png')
        
##     return


    
## def fig_roc_all(cross_data_path, nState, threshold_mult, prefixes, opr='robot', attr='id'):
        
##     import itertools
##     colors = itertools.cycle(['g', 'm', 'c', 'k'])
##     shapes = itertools.cycle(['x','v', 'o', '+'])
    
##     pp.figure()    
##     ## pp.title("ROC of anomaly detection ")
##     for i, prefix in enumerate(prefixes):

##         cross_test_path = os.path.join(cross_data_path, 'multi_'+prefix, str(nState))
        
##         fp_l = []
##         err_l = []
##         for ths in threshold_mult:
##             res_file   = prefix+'_roc_'+opr+'_'+'ths_'+str(ths)+'.pkl'
##             res_file   = os.path.join(cross_test_path, res_file)

##             d = ut.load_pickle(res_file)
##             fp  = d['fp'] 
##             err = d['err']         

##             fp_l.append([fp])
##             err_l.append([err])

##         fp_l  = np.array(fp_l)*100.0

##         color = colors.next()
##         shape = shapes.next()

##         if i==0:
##             semantic_label='Known mechanism \n class -'+prefix
##         else:
##             semantic_label='Known mechanism \n identity -'+prefix
            
##         pp.plot(fp_l, err_l, '--'+shape+color, label= semantic_label, mec=color, ms=8, mew=2)

##     pp.legend(loc=0,prop={'size':14})

##     pp.xlabel('False positive rate (percentage)')
##     pp.ylabel('Mean excess log likelihood')    
##     pp.show()
        
