import numpy as np
import pymc3 as pm
from matplotlib.patches import Ellipse
from scipy import stats
import matplotlib as plt



def fit_mvn_param(y, niter=100):

    import theano.tensor as T

    n_dim = np.shape(y)[-1]

    with pm.Model() as mvn:
        # priors on standard deviation
        sigma = pm.Lognormal('sigma', mu=np.zeros(n_dim), tau=np.ones(n_dim), shape=n_dim)
        # prior on LKJ shape
        nu = pm.Uniform('nu', 0, 5)
        # LKJ prior for correlation matrix as upper triangular vector
        C_triu = pm.LKJCorr('C_triu', n=nu, p=n_dim)
        # convert to matrix form
        C = T.fill_diagonal(C_triu[np.zeros((n_dim,n_dim), 'int')], 1)
        sigma_diag = T.nlinalg.diag(sigma)
        # indduced covariance matrix
        cov = pm.Deterministic('cov', T.nlinalg.matrix_dot(sigma_diag, C, sigma_diag))
        tau = pm.Deterministic('tau', T.nlinalg.matrix_inverse(cov))
        mu = pm.MvNormal('mu', mu=0, tau=tau, shape=n_dim)
        print mu, tau, np.shape(y)

        Y_obs_ = pm.MvNormal('Y_obs', mu=mu, tau=tau, observed=y)

        start = pm.find_MAP()

        trace = pm.sample(niter, start=start)

    burn = niter//2
    trace = trace[burn:]
    mu_hat = trace['mu'].mean(0)
    cov_hat = trace['cov'].mean(0)

    return mu_hat, cov_hat
