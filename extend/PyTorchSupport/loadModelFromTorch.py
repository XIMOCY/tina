import torch
import os

def loadModelFromTorch(model_path):
    model = torch.load(model_path)
    return model