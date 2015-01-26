#!/usr/local/bin/python

import sys, os, copy
import numpy as np, math
import scipy as scp

import roslib; roslib.load_manifest('hrl_anomaly_detection')
import rospy
import inspect
import warnings
import random

# Util
import hrl_lib.util as ut
## import cPickle
## from sklearn.externals import joblib

# Matplot
import matplotlib
import matplotlib.pyplot as plt
from matplotlib import gridspec
from matplotlib import animation

## import door_open_data as dod
import ghmm
from scipy.stats import norm
from sklearn.cross_validation import train_test_split
from sklearn.metrics import r2_score
from sklearn.base import clone
from sklearn import cross_validation
from scipy import optimize
## from pysmac.optimize import fmin                
from joblib import Parallel, delayed
## from scipy.optimize import fsolve
## from scipy import interpolate
from scipy import interpolate

from learning_base import learning_base
import sandbox_dpark_darpa_m3.lib.hrl_dh_lib as hdl


class learning_hmm_multi(learning_base):
    def __init__(self, nState, nFutureStep=5, nCurrentStep=10, \
                 trans_type="left_right"):

        learning_base.__init__(self, trans_type)

        ## Tunable parameters                
        self.nState= nState # the number of hidden states
        self.nFutureStep = nFutureStep
        self.nCurrentStep = nCurrentStep
        
        ## Un-tunable parameters
        self.trans_type = trans_type #"left_right" #"full"
        self.A = None # transition matrix        
        self.B = None # emission matrix        
                
        # emission domain of this model        
        self.F = ghmm.Float()  
               
        # Assign local functions
        learning_base.__dict__['fit'] = self.fit        
        learning_base.__dict__['predict'] = self.predict
        learning_base.__dict__['score'] = self.score                
        pass

        
    #----------------------------------------------------------------------        
    #
    def fit(self, aXData1, aXData2, A=None, B=None, pi=None, B_dict=None, verbose=False):

        if A is None:        
            if verbose: print "Generate new A matrix"                
            # Transition probability matrix (Initial transition probability, TODO?)
            A = self.init_trans_mat(self.nState).tolist()

        if B is None:
            if verbose: print "Generate new B matrix"                                            
            # We should think about multivariate Gaussian pdf.  

            self.mu1, self.mu2, self.cov = self.vectors_to_mean_cov(aXData1, aXData2, self.nState)

            # Emission probability matrix
            B = np.hstack([self.mu, self.sig]).tolist() # Must be [i,:] = [mu, sig]
                
        if pi is None:            
            # pi - initial probabilities per state 
            ## pi = [1.0/float(self.nState)] * self.nState
            pi = [0.] * self.nState
            pi[0] = 1.0

        # HMM model object
        self.ml = ghmm.HMMFromMatrices(self.F, ghmm.MultivariateGaussianDistribution(self.F), A, B, pi)
        
        ## print "Run Baum Welch method with (samples, length)", X_train.shape
        train_seq = X_train.tolist()
        final_seq = ghmm.SequenceSet(self.F, train_seq)        
        self.ml.baumWelch(final_seq, 10000)

        [self.A,self.B,self.pi] = self.ml.asMatrices()
        self.A = np.array(self.A)
        self.B = np.array(self.B)

        ## self.mean_path_plot(mu[:,0], sigma[:,0])        
        ## print "Completed to fitting", np.array(final_seq).shape
        
        # state range
        self.state_range = np.arange(0, self.nState, 1)

        # Pre-computation for PHMM variables
        self.mu_z   = np.zeros((self.nState))
        self.mu_z2  = np.zeros((self.nState))
        self.mu_z3  = np.zeros((self.nState))
        self.var_z  = np.zeros((self.nState))
        self.sig_z3 = np.zeros((self.nState))
        for i in xrange(self.nState):
            zp             = self.A[i,:]*self.state_range
            self.mu_z[i]   = np.sum(zp)
            self.mu_z2[i]  = self.mu_z[i]**2
            #self.mu_z3[i]  = self.mu_z[i]**3
            self.var_z[i]  = np.sum(zp*self.state_range) - self.mu_z[i]**2
            #self.sig_z3[i] = self.var_z[i]**(1.5)


    #----------------------------------------------------------------------
    # Returns the mean accuracy on the given test data and labels.
    def score(self, X_test, **kwargs):

        if self.ml is None: 
            print "No ml!!"
            return -5.0        
        
        # Get input
        if type(X_test) == np.ndarray:
            X=X_test.tolist()

        sample_weight=None # TODO: future input
        
        #
        n = len(X)
        nCurrentStep = [5,10,15,20,25]
        nFutureStep = 1

        total_score = np.zeros((len(nCurrentStep)))
        for j, nStep in enumerate(nCurrentStep):

            self.nCurrentStep = nStep
            X_next = np.zeros((n))
            X_pred = np.zeros((n))
            mu_pred  = np.zeros((n))
            var_pred = np.zeros((n))
            
            for i in xrange(n):
                if len(X[i]) > nStep+nFutureStep: #Full data                
                    X_past = X[i][:nStep]
                    X_next[i] = X[i][nStep]
                else:
                    print "Error: input should be full length data!!"
                    sys.exit()

                mu, var = self.one_step_predict(X_past)
                mu_pred[i] = mu[0]
                var_pred[i] = var[0]

            total_score[j] = r2_score(X_next, mu_pred, sample_weight=sample_weight)

        ## print "---------------------------------------------"
        ## print "Total Score"
        ## print total_score
        ## print "---------------------------------------------"
        return sum(total_score) / float(len(nCurrentStep))
        
        
    #----------------------------------------------------------------------        
    #                
    # Returns mu,sigma for n hidden-states from feature-vector
    def vectors_to_mean_cov(self,vec1, vec2, nState): 

        if len(vec1[0]) != len(vec2[0]):
            print "data length different!!! ", len(vec1[0]), len(vec2[0])
            sys.exit()

                    
        index = 0
        m,n = np.shape(vec1)
        ## print m,n
        mult = 2

        o_x = np.arange(0.0, n, 1.0)
        o_mu1  = scp.mean(vec1, axis=0)
        o_sig1 = scp.std(vec1, axis=0)
        o_mu2  = scp.mean(vec2, axis=0)
        o_sig2 = scp.std(vec2, axis=0)
        o_cov  = np.zeros((n,2,2))

        for i in xrange(n):
            o_cov[i] = np.cov(np.concatenate((vec1[:,i],vec2[:,i]),axis=0))
        
        f_mu1  = interpolate.interp1d(o_x, o_mu1, kind='linear')
        f_sig1 = interpolate.interp1d(o_x, o_sig1, kind='linear')
        f_mu2  = interpolate.interp1d(o_x, o_mu2, kind='linear')
        f_sig2 = interpolate.interp1d(o_x, o_sig2, kind='linear')

        f_cov11 = interpolate.interp1d(o_x, o_cov[:,0,0], kind='linear')
        f_cov12 = interpolate.interp1d(o_x, o_cov[:,0,1], kind='linear')
        f_cov21 = interpolate.interp1d(o_x, o_cov[:,1,0], kind='linear')
        f_cov22 = interpolate.interp1d(o_x, o_cov[:,1,1], kind='linear')

            
        x = np.arange(0.0, float(n-1)+1.0/float(mult), 1.0/float(mult))
        mu1  = f_mu1(x)
        sig1 = f_sig1(x)
        mu2  = f_mu2(x)
        sig2 = f_sig2(x)

        cov11 = f_cov11(x)
        cov12 = f_cov12(x)
        cov21 = f_cov21(x)
        cov22 = f_cov22(x)
        
        while len(mu1) != nState:

            d_mu1  = np.abs(mu1[1:] - mu1[:-1]) # -1 length 
            d_sig1 = np.abs(sig1[1:] - sig1[:-1]) # -1 length 
            idx = d_sig1.tolist().index(min(d_sig1))
            
            mu1[idx]  = (mu1[idx]+mu1[idx+1])/2.0
            sig1[idx] = (sig1[idx]+sig1[idx+1])/2.0
            mu2[idx]  = (mu2[idx]+mu2[idx+1])/2.0
            sig2[idx] = (sig2[idx]+sig2[idx+1])/2.0
            
        
            mu  = scp.delete(mu,idx+1)
            sig = scp.delete(sig,idx+1)

        mu = mu.reshape((len(mu),1))
        sig = sig.reshape((len(sig),1))

        
        ## import matplotlib.pyplot as pp
        ## pp.figure()
        ## pp.plot(mu)
        ## pp.plot(mu+1.*sig)
        ## pp.plot(scp.mean(vec, axis=0), 'r')
        ## pp.show()
        ## sys.exit()


    ## index = 0
    ## m,n = np.shape(fvec1)
    ## #print m,n
    ## mu_1 = np.zeros((20,1))
    ## mu_2 = np.zeros((20,1))
    ## cov = np.zeros((20,2,2))
    ## DIVS = m/20

    ## while (index < 20):
    ##     m_init = index*DIVS
    ##     temp_fvec1 = fvec1[(m_init):(m_init+DIVS),0:]
    ##     temp_fvec2 = fvec2[(m_init):(m_init+DIVS),0:]
    ##     temp_fvec1 = np.reshape(temp_fvec1,DIVS*n)
    ##     temp_fvec2 = np.reshape(temp_fvec2,DIVS*n)
    ##     mu_1[index] = np.mean(temp_fvec1)
    ##     mu_2[index] = np.mean(temp_fvec2)
    ##     cov[index,:,:] = np.cov(np.concatenate((temp_fvec1,temp_fvec2),axis=0))
    ##     if index == 0:
    ##         print 'mean = ', mu_2[index]
    ##         print 'mean = ', scp.mean(fvec2[(m_init):(m_init+DIVS),0:])
    ##         print np.shape(np.concatenate((temp_fvec1,temp_fvec2),axis=0))
    ##         print cov[index,:,:]
    ##         print scp.std(fvec2[(m_init):(m_init+DIVS),0:])
    ##         print scp.std(temp_fvec2)
    ##     index = index+1
        
    ## return mu_1,mu_2,cov


        
        return mu,sig
