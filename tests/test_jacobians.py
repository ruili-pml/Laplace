import pytest
import torch
from torch import nn

from laplace.curvature import AsdlInterface, BackPackInterface, CurvatureInterface
from laplace.utils import FeatureExtractor
from tests.utils import jacobians_naive


@pytest.fixture
def multioutput_model():
    model = torch.nn.Sequential(nn.Linear(3, 20), nn.Linear(20, 2))
    setattr(model, 'output_size', 2)
    return model


@pytest.fixture
def singleoutput_model():
    model = torch.nn.Sequential(nn.Linear(3, 20), nn.Linear(20, 1))
    setattr(model, 'output_size', 1)
    return model


@pytest.fixture
def linear_model():
    model = torch.nn.Sequential(nn.Linear(3, 1, bias=False))
    setattr(model, 'output_size', 1)
    return model


@pytest.fixture
def X():
    torch.manual_seed(15)
    return torch.randn(200, 3)


@pytest.mark.parametrize(
    'backend_cls', [CurvatureInterface, AsdlInterface, BackPackInterface]
)
def test_linear_jacobians(linear_model, X, backend_cls):
    # jacobian of linear model is input X.
    backend = backend_cls(linear_model, 'classification')
    Js, f = backend.jacobians(X)
    # into Jacs shape (batch_size, output_size, params)
    true_Js = X.reshape(len(X), 1, -1)
    assert true_Js.shape == Js.shape
    assert torch.allclose(true_Js, Js, atol=1e-5)
    assert torch.allclose(f, linear_model(X), atol=1e-5)


@pytest.mark.parametrize(
    'backend_cls', [CurvatureInterface, AsdlInterface, BackPackInterface]
)
def test_jacobians_singleoutput(singleoutput_model, X, backend_cls):
    model = singleoutput_model
    backend = backend_cls(model, 'classification')
    Js, f = backend.jacobians(X)
    Js_naive, f_naive = jacobians_naive(model, X)
    assert Js.shape == Js_naive.shape
    assert torch.abs(Js - Js_naive).max() < 1e-6
    assert torch.allclose(model(X), f_naive)
    assert torch.allclose(f, f_naive)


@pytest.mark.parametrize(
    'backend_cls', [CurvatureInterface, AsdlInterface, BackPackInterface]
)
def test_jacobians_multioutput(multioutput_model, X, backend_cls):
    model = multioutput_model
    backend = backend_cls(model, 'classification')
    Js, f = backend.jacobians(X)
    Js_naive, f_naive = jacobians_naive(model, X)
    assert Js.shape == Js_naive.shape
    assert torch.abs(Js - Js_naive).max() < 1e-6
    assert torch.allclose(model(X), f_naive)
    assert torch.allclose(f, f_naive)


@pytest.mark.parametrize(
    'backend_cls', [CurvatureInterface, AsdlInterface, BackPackInterface]
)
def test_last_layer_jacobians_singleoutput(singleoutput_model, X, backend_cls):
    model = FeatureExtractor(singleoutput_model)
    backend = backend_cls(model, 'classification')
    Js, f = backend.last_layer_jacobians(X)
    _, phi = model.forward_with_features(X)
    Js_naive, f_naive = jacobians_naive(model.last_layer, phi)
    assert Js.shape == Js_naive.shape
    assert torch.abs(Js - Js_naive).max() < 1e-6
    assert torch.allclose(model(X), f_naive)
    assert torch.allclose(f, f_naive)


@pytest.mark.parametrize(
    'backend_cls', [CurvatureInterface, AsdlInterface, BackPackInterface]
)
def test_last_layer_jacobians_multioutput(multioutput_model, X, backend_cls):
    model = FeatureExtractor(multioutput_model)
    backend = backend_cls(model, 'classification')
    Js, f = backend.last_layer_jacobians(X)
    _, phi = model.forward_with_features(X)
    Js_naive, f_naive = jacobians_naive(model.last_layer, phi)
    assert Js.shape == Js_naive.shape
    assert torch.abs(Js - Js_naive).max() < 1e-6
    assert torch.allclose(model(X), f_naive)
    assert torch.allclose(f, f_naive)


@pytest.mark.parametrize('backend_cls', [CurvatureInterface, BackPackInterface])
def test_backprop_jacobians_singleoutput(singleoutput_model, X, backend_cls):
    X.requires_grad = True
    backend = backend_cls(singleoutput_model, 'regression')

    try:
        Js, f = backend.jacobians(X, enable_backprop=True)
        grad_X_f = torch.autograd.grad(f.sum(), X)[0]

        Js, f = backend.jacobians(X, enable_backprop=True)
        grad_X_Js = torch.autograd.grad(Js.sum(), X)[0]

        assert grad_X_f.shape == X.shape
        assert grad_X_Js.shape == X.shape
    except RuntimeError:
        assert False


@pytest.mark.parametrize('backend_cls', [CurvatureInterface, BackPackInterface])
def test_backprop_jacobians_multioutput(multioutput_model, X, backend_cls):
    X.requires_grad = True
    backend = backend_cls(multioutput_model, 'regression')

    try:
        Js, f = backend.jacobians(X, enable_backprop=True)
        grad_X_f = torch.autograd.grad(f.sum(), X)[0]

        X.grad = None
        Js, f = backend.jacobians(X, enable_backprop=True)
        grad_X_Js = torch.autograd.grad(Js.sum(), X)[0]

        assert grad_X_f.shape == X.shape
        assert grad_X_Js.shape == X.shape
    except RuntimeError:
        assert False


@pytest.mark.parametrize('backend_cls', [CurvatureInterface, BackPackInterface])
def test_backprop_last_layer_jacobians_singleoutput(singleoutput_model, X, backend_cls):
    X.requires_grad = True
    backend = backend_cls(
        FeatureExtractor(singleoutput_model, enable_backprop=True), 'regression'
    )

    try:
        Js, f = backend.last_layer_jacobians(X)
        grad_X_f = torch.autograd.grad(f.sum(), X)[0]

        Js, f = backend.last_layer_jacobians(X)
        grad_X_Js = torch.autograd.grad(Js.sum(), X)[0]

        assert grad_X_f.shape == X.shape
        assert grad_X_Js.shape == X.shape
    except RuntimeError:
        assert False


@pytest.mark.parametrize('backend_cls', [CurvatureInterface, BackPackInterface])
def test_backprop_last_layer_jacobians_multioutput(multioutput_model, X, backend_cls):
    X.requires_grad = True
    backend = backend_cls(
        FeatureExtractor(multioutput_model, enable_backprop=True), 'regression'
    )

    try:
        Js, f = backend.last_layer_jacobians(X)
        grad_X_f = torch.autograd.grad(f.sum(), X)[0]

        Js, f = backend.last_layer_jacobians(X)
        grad_X_Js = torch.autograd.grad(Js.sum(), X)[0]

        assert grad_X_f.shape == X.shape
        assert grad_X_Js.shape == X.shape
    except RuntimeError:
        assert False
