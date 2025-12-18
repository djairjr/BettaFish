import torch
import torch.nn as nn

class AdapterLayer(nn.Module):
    """Adapter layer implementation
    Adding it to the Transformer layer can achieve efficient fine-tuning of parameters"""
    def __init__(self, input_size, adapter_size):
        super(AdapterLayer, self).__init__()
        # Dimensionality reduction fully connected layer
        self.down_project = nn.Linear(input_size, adapter_size)
        # activation function
        self.activation = nn.ReLU()
        # Upgraded dimension fully connected layer
        self.up_project = nn.Linear(adapter_size, input_size)
        
        # Initialization parameters
        self._init_weights()
    
    def _init_weights(self):
        # Initialize down_project with a smaller value
        nn.init.normal_(self.down_project.weight, std=1e-2)
        nn.init.zeros_(self.down_project.bias)
        
        # Initialize up_project to a value close to zero to ensure that it has little impact on the original model in the early stages of training.
        nn.init.normal_(self.up_project.weight, std=1e-2)
        nn.init.zeros_(self.up_project.bias)
    
    def forward(self, x):
        # Save original input for residual connection
        residual = x
        
        # through dimensionality reduction layer
        x = self.down_project(x)
        # activation
        x = self.activation(x)
        # Through the dimensionality enhancement layer
        x = self.up_project(x)
        
        # residual connection
        return residual + x 