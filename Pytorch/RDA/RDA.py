#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Mar 25 13:45:45 2019

@author: huiminren
"""

import torch
import torch.utils.data as Data
from torchvision.utils import save_image
from torch import nn
import matplotlib.pyplot as plt
import numpy as np
import os
import time

from BasicAutoencoder.DA import AE_Net as AENET
from BasicAutoencoder.DA import Autoencoder
from BasicAutoencoder.VAE import VAE_Net
from BasicAutoencoder.VAE import Autoencoder2
from shrink import l1shrink as SHR 

import glob
from skimage.util import random_noise
from utils import *



def corrupt(X_in,corNum=10):
    X = X_in.clone()
    N,p = X.shape[0],X.shape[1]
    for i in range(N):
        loclist = np.random.randint(0, p, size = corNum)
        for j in loclist:
            if X[i,j] > 0.5:
                X[i,j] = 0
            else:
                X[i,j] = 1
    return X

class RobustDAE(object):
    """
    @Original author: Chong Zhou
    
    Des:
        X = L + S
        L is a non-linearly low rank matrix and S is a sparse matrix.
        argmin ||L - Decoder(Encoder(L))|| + ||S||_1
        Use Alternating projection to train model
    """
    def __init__(self,lambda_=1.0,error = 1e-7,use_cuda=True, nz=100, ngf=64, ndf=64, nc=3):
        self.errors = []
        self.error = error
        self.lambda_ = lambda_
        self.ae = Autoencoder()
        cuda = use_cuda and torch.cuda.is_available() 
        self.device = torch.device("cuda" if cuda else "cpu") #asign cuda
        self.dae = AENET(nc, ngf, ndf, nz)
        if torch.cuda.device_count() > 1: # if have multiple GPUs, set data parallel to model
            print("Let's use", torch.cuda.device_count(), "GPUs!")
            self.dae = nn.DataParallel(self.dae)
        self.dae.to(self.device)
        return
    
    def fit(self,train_dataset, path, model_name, iteration = 30, batch_size = 128, 
            learning_rate = 1e-4, epochs = 20, verbose=False):
        # Initialize L, S dtyp: tensor
        X = train_dataset.tensors[0]
        self.L = torch.zeros(X.size())
        self.S = torch.zeros(X.size())
        
        # Calculate mu(shrinkage operator)
        X_numpy = X.detach().cpu().numpy()
#        mu = (X_numpy.size)/(4.0*np.linalg.norm(X_numpy,1))
        mu = (X_numpy.size)/(4.0*np.linalg.norm(X_numpy.reshape(-1,X_numpy.shape[-1]*X_numpy.shape[-1]),1))
        print("Shrink parameter:", self.lambda_/mu)
        LS0 = self.L + self.S
        
        XFnorm = torch.norm(X,'fro') # Frobenius norm
        if verbose:
            print("X shape:",X.shape)
            print("mu:",mu)
            print("XFnorm:", XFnorm)
        
        for it in range (iteration):
            print('iteration:',it)
            if verbose:
                print("Out iteration:", it)
                
            self.L = X - self.S
            # Convert L to trian_loader
            ae_dataset = Data.TensorDataset(self.L)
            ae_train_loader = Data.DataLoader(dataset = ae_dataset, batch_size = batch_size, shuffle = True)
                
            # Use L to train autoencoder and get optimized(reconstructed) L
            model = self.ae.train(device = self.device, model = self.dae,
                    train_loader = ae_train_loader, learning_rate = learning_rate,epochs = epochs)
            recon_loader = Data.DataLoader(dataset = ae_dataset,batch_size = 1, shuffle = False)
            self.L = self.ae.reconstruction(self.device, model, recon_loader).detach().cpu()
            # Alternate project of S
            self.S = SHR.shrink(self.lambda_/mu,(X-self.L).reshape(-1)).reshape(X.shape)
            
            # Break criterion 1: L and S are close enought to X
            c1 = torch.norm((X - self.L - self.S),'fro') / XFnorm
            # Break criterion 2: there is no change for L and S
            c2 = np.min([mu,np.sqrt(mu)]) * torch.norm(LS0 - self.L - self.S) / XFnorm
            self.errors.append(c1)
                       
            if it == iteration - 1:
                print("save autoencoder:")
                torch.save(model.state_dict(), path+'model_rda_'+model_name+'.pth') 
                # plots
                print("plot examples of reconstruction:")
                self.plot(path,X[:10],self.L[:10])
            if verbose:
                print("c1:",c1)
                print("c2:",c2)
            
            if c1 < self.error and c2 < self.error:
                print("early break")
                break
            
            LS0 = self.L + self.S
            
        return self.L
        
    def plot(self,path,view_data,decoded_data):
        save_image(view_data.data, path+'raw_face.jpg',nrow=10, padding=2)
        save_image(decoded_data.data, path+'recon_face.jpg',nrow=10, padding=2)
#        # initialize figure
#        f, a = plt.subplots(2, 10, figsize=(5, 2)) #
#        for i in range(10):
#            a[0][i].imshow(np.transpose(view_data.data.numpy()[i],(1,2,0)))
#            a[0][i].set_xticks(()); a[0][i].set_yticks(())
#            a[1][i].clear()
#            a[1][i].imshow(np.transpose(decoded_data.data.numpy()[i],(1,2,0)))
#            a[1][i].set_xticks(()); a[1][i].set_yticks(())
#        plt.savefig(path+"eg_recon.png")
#        plt.show()
            
#===================================================
def main(lambda_, noise_factor, debug=True):
    start_time = time.time()
    torch.manual_seed(595)
    ngf = 64
    ndf = 64
    nz = 100
    nc = 3
    
    learning_rate = 1e-4
    batch_size = 128
    iteration = 10
    epochs = 20
    vae_epochs = 200
    
    if debug:
        iteration = 1
        epochs = 1
        vae_epochs = 1
    
    path = "rda/"
    if not os.path.isdir(path):
        os.mkdir(path)
    if not os.path.exists(path):
        os.mkdir(path)
    path = path+"lambda_"+str(lambda_)+"/"
    if not os.path.exists(path):
        os.mkdir(path)
    path = path+"noise_"+str(noise_factor)+"/"
    if not os.path.exists(path):
        os.mkdir(path)
    
    data_files = glob.glob(os.path.join("./img_align_celeba", "*.jpg"))
    data_files = sorted(data_files)
    data_files = np.array(data_files)
    x_train = np.array([get_image(data_file, 148) for data_file in data_files])
    x_train_noisy = random_noise(x_train, mode='s&p', amount = noise_factor)
    x_train_noisy = np.transpose(x_train_noisy,(0,3,1,2)).astype(np.float32)
    
    x_train_noisy = torch.tensor(x_train_noisy)
    train_dataset = Data.TensorDataset(x_train_noisy)
    print("RDA denoising:")
    rda = RobustDAE(lambda_ = lambda_, nz = nz, ngf = ngf, ndf = ndf, nc = nc)
    L = rda.fit(train_dataset, path = path, model_name = str(noise_factor), 
                iteration = iteration, batch_size = batch_size, 
                learning_rate = learning_rate, epochs = epochs)
    
    vae_dataset = Data.TensorDataset(L)
    vae_loader = Data.DataLoader(vae_dataset, batch_size=128, shuffle=True,num_workers=2)  
                       
    # load Neural Network
    net = VAE_Net(nc, ngf, ndf, nz)
    if torch.cuda.device_count() > 1: # if have multiple GPUs, set data parallel to model
        print("Let's use", torch.cuda.device_count(), "GPUs!")
        net = nn.DataParallel(net)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    net.to(device)
    
    print("VAE generation:")
    # train model
    vae = Autoencoder2()
    model = vae.train(device = device, model = net, train_loader = vae_loader, 
                     learning_rate = learning_rate, epochs = vae_epochs)
    
    # get reconstruction
    recon_loader = Data.DataLoader(vae_dataset[:100], batch_size=1, shuffle=False,num_workers=2)
    vae.reconstruction(device=device, model=model, dataloader=recon_loader)
    
    # get generation
    vae.generation_eg(device=device, model=model, path=path)

    np.save(path+'running_time.npy',np.array(time.time()-start_time))
    
    
if __name__ == "__main__":
    lambdas = [300]#[1, 10, 50, 70, 100, 150]
    for lambda_ in lambdas:
        noise_factors = [.2]#[.0, .05, .1, .15, .2, .25, .3, .35, .4, .45, .5]
        for noise_factor in noise_factors:
            print(noise_factor)
            main(lambda_=lambda_, noise_factor = noise_factor, debug=True)
    
    
    
    
