from laplace.baselaplace import FullLaplace
from laplace.curvature.backpack import BackPackGGN
import numpy as np
import torch

from laplace import Laplace, marglik_training

from helper.dataloaders import get_sinusoid_example
from helper.util import plot_regression


n_epochs = 1000
torch.manual_seed(711)

# create toy regression data
X_train, y_train, train_loader, X_test = get_sinusoid_example(sigma_noise=0.3)

# construct single layer neural network
def get_model():
    torch.manual_seed(711)
    return torch.nn.Sequential(
        torch.nn.Linear(1, 50), torch.nn.Tanh(), torch.nn.Linear(50, 1)
    )
model = get_model()

# train MAP
criterion = torch.nn.MSELoss()
optimizer = torch.optim.Adam(model.parameters(), lr=1e-2)
for i in range(n_epochs):
    for X, y in train_loader:
        optimizer.zero_grad()
        loss = criterion(model(X), y)
        loss.backward()
        optimizer.step()

la = Laplace(model, 'regression', subset_of_weights='all', hessian_structure='full')
la.fit(train_loader)
log_prior, log_sigma = torch.ones(1, requires_grad=True), torch.ones(1, requires_grad=True)
hyper_optimizer = torch.optim.Adam([log_prior, log_sigma], lr=1e-1)
for i in range(n_epochs):
    hyper_optimizer.zero_grad()
    neg_marglik = - la.log_marginal_likelihood(log_prior.exp(), log_sigma.exp())
    neg_marglik.backward()
    hyper_optimizer.step()

# Serialization for fitted quantities
state_dict = la.state_dict()
torch.save(state_dict, 'state_dict.bin')

la = Laplace(model, 'regression', subset_of_weights='all', hessian_structure='full')
# Load serialized, fitted quantities
la.load_state_dict(torch.load('state_dict.bin'))

print(f'sigma={la.sigma_noise.item():.2f}',
      f'prior precision={la.prior_precision.item():.2f}')

x = X_test.flatten().cpu().numpy()

# Two options:
# 1.) Marginal predictive distribution N(f_map(x_i), var(x_i))
# The mean is (m,k), the var is (m,k,k)
f_mu, f_var = la(X_test)

# 2.) Joint pred. dist. N((f_map(x_1),...,f_map(x_m)), Cov(f(x_1),...,f(x_m)))
# The mean is (m*k,) where k is the output dim. The cov is (m*k,m*k)
f_mu_joint, f_cov = la(X_test, joint=True)

# Both should be true
assert torch.allclose(f_mu.flatten(), f_mu_joint)
assert torch.allclose(f_var.flatten(), f_cov.diag())

f_mu = f_mu.squeeze().detach().cpu().numpy()
f_sigma = f_var.squeeze().detach().sqrt().cpu().numpy()
pred_std = np.sqrt(f_sigma**2 + la.sigma_noise.item()**2)

plot_regression(X_train, y_train, x, f_mu, pred_std,
                file_name='regression_example', plot=True)

# alternatively, optimize parameters and hyperparameters of the prior jointly
model = get_model()
la, model, margliks, losses = marglik_training(
    model=model, train_loader=train_loader, likelihood='regression',
    hessian_structure='full', backend=BackPackGGN, n_epochs=n_epochs,
    optimizer_kwargs={'lr': 1e-2}, prior_structure='scalar'
)

print(f'sigma={la.sigma_noise.item():.2f}',
      f'prior precision={la.prior_precision.numpy()}')

f_mu, f_var = la(X_test)
f_mu = f_mu.squeeze().detach().cpu().numpy()
f_sigma = f_var.squeeze().sqrt().cpu().numpy()
pred_std = np.sqrt(f_sigma**2 + la.sigma_noise.item()**2)
plot_regression(X_train, y_train, x, f_mu, pred_std,
                file_name='regression_example_online', plot=False)
