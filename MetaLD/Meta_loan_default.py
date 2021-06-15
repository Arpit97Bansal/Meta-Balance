

import warnings
warnings.filterwarnings('ignore')
import pandas as pd
import numpy as np
import os
import matplotlib.pyplot as plt
import seaborn as sn
import itertools
from collections import Counter
np.random.seed(2)
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import confusion_matrix, accuracy_score, precision_score, f1_score, recall_score, matthews_corrcoef, roc_auc_score

from imblearn.over_sampling import SMOTE, SMOTENC, BorderlineSMOTE, SVMSMOTE, ADASYN, RandomOverSampler
from imblearn.under_sampling import ClusterCentroids, RandomUnderSampler, NearMiss, AllKNN
from imblearn.combine import SMOTEENN


from torch.autograd import Variable
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader
from torch.utils.data import Dataset, TensorDataset


import torch.utils.data as data_utils
import torchvision
import random
import json


class ImbalancedDatasetSampler(torch.utils.data.sampler.Sampler):
    """Samples elements randomly from a given list of indices for imbalanced dataset
    Arguments:
        indices (list, optional): a list of indices
        num_samples (int, optional): number of samples to draw
        callback_get_label func: a callback-like function which takes two arguments - dataset and index
    """

    def __init__(self, dataset, indices=None, num_samples=None, callback_get_label=None):
                
        # if indices is not provided, 
        # all elements in the dataset will be considered
        self.indices = list(range(len(dataset))) \
            if indices is None else indices

        # define custom callback
        self.callback_get_label = callback_get_label

        # if num_samples is not provided, 
        # draw `len(indices)` samples in each iteration
        self.num_samples = len(self.indices) \
            if num_samples is None else num_samples
            
        # distribution of classes in the dataset 
        label_to_count = {}
        for idx in self.indices:
            label = self._get_label(dataset, idx)
            if label in label_to_count:
                label_to_count[label] += 1
            else:
                label_to_count[label] = 1

        print(label_to_count)               
        # weight for each sample
        weights = [1.0 / label_to_count[self._get_label(dataset, idx)]
                   for idx in self.indices]
        self.weights = torch.DoubleTensor(weights)

    def _get_label(self, dataset, idx):
        return dataset[idx][1].item()
                
    def __iter__(self):
        return (self.indices[i] for i in torch.multinomial(
            self.weights, self.num_samples, replacement=True))

    def __len__(self):
        return self.num_samples

class BalancedBatchSampler(torch.utils.data.sampler.Sampler):
    def __init__(self, dataset, labels=None):
        self.labels = labels
        self.dataset = dict()
        self.balanced_max = 0
        # Save all the indices for all the classes
        for idx in range(0, len(dataset)):
            label = self._get_label(dataset, idx)
            if label not in self.dataset:
                self.dataset[label] = list()
            self.dataset[label].append(idx)
            self.balanced_max = len(self.dataset[label]) \
                if len(self.dataset[label]) > self.balanced_max else self.balanced_max
        
        # Oversample the classes with fewer elements than the max
        for label in self.dataset:
            while len(self.dataset[label]) < self.balanced_max:
                self.dataset[label].append(random.choice(self.dataset[label]))
        self.keys = list(self.dataset.keys())
        self.currentkey = 0
        self.indices = [-1]*len(self.keys)

    def __iter__(self):
        while self.indices[self.currentkey] < self.balanced_max - 1:
            self.indices[self.currentkey] += 1
            yield self.dataset[self.keys[self.currentkey]][self.indices[self.currentkey]]
            self.currentkey = (self.currentkey + 1) % len(self.keys)
        self.indices = [-1]*len(self.keys)
    
    def _get_label(self, dataset, idx, labels = None):
        return dataset[idx][1].item()

    def __len__(self):
        return self.balanced_max*len(self.keys)

class trainData(Dataset):
    
    def __init__(self, X_data, y_data):
        self.X_data = X_data
        self.y_data = y_data
        
    def __getitem__(self, index):
        return self.X_data[index], self.y_data[index]
        
    def __len__ (self):
        return len(self.X_data)

class SimpleNet(nn.Module):
    def __init__(self):
        super(SimpleNet, self).__init__()
        self.model = nn.Sequential(
            nn.Linear(12, 16),
            nn.ReLU(),
            nn.Linear(16, 24),
            nn.ReLU(),

            nn.Dropout(p=0.5),

            nn.Linear(24, 20),
            nn.ReLU(),
            nn.Linear(20, 24),
            nn.ReLU(),
            nn.Linear(24, 1),

            #nn.Sigmoid()

            )

    def forward(self, x):
        x = self.model(x)
        return x

def binary_acc(y_pred, y_test):
    y_pred_tag = torch.round(torch.sigmoid(y_pred))

    correct_results_sum = (y_pred_tag == y_test).sum().float()
    acc = correct_results_sum/y_test.shape[0]
    acc = torch.round(acc * 100)
    
    return acc.item()

from torch.optim import SGD, Optimizer
from torch.optim.lr_scheduler import StepLR

def plot_confusion_matrix(cm, classes,
                          normalize=False,
                          title='Confusion Matrix',
                          cmap=plt.cm.Blues):
    """
    This function prints and plots the confusion matrix.
    Normalization can be applied by setting `normalize=True`.
    """
    if normalize:
        cm = cm.astype('float') / cm.sum(axis=1)[:, np.newaxis]
        print("Normalized confusion matrix")
    else:
        print('Confusion matrix, without normalization')

    plt.imshow(cm, interpolation='nearest', cmap=cmap)
    plt.title(title)
    plt.colorbar()
    tick_marks = np.arange(len(classes))
    plt.xticks(tick_marks, classes, rotation=0)
    plt.yticks(tick_marks, classes)

    fmt = '.2f' if normalize else 'd'
    thresh = cm.max() / 2.
    for i, j in itertools.product(range(cm.shape[0]), range(cm.shape[1])):
        plt.text(j, i, format(cm[i, j], fmt),
                 horizontalalignment="center",
                 color="white" if cm[i, j] > thresh else "black")

    plt.ylabel('True label')
    plt.xlabel('Predicted label')
    plt.tight_layout()

def get_val_batch(data_loader, iterator):
  try:
    task_data = iterator.next() 
  except StopIteration:
    iterator = iter(data_loader)
    task_data = iterator.next()
    
  inputs, labels = task_data
  #print(type(labels))
  #print(labels.shape)

  return inputs , labels, iterator

def train(inner_lr, meta_batch_update_factor):

  batch_losses = []

  model = SimpleNet()
  model = model.cuda()
  num_epochs = 100

  criterion = nn.BCEWithLogitsLoss()

  optimizer = torch.optim.SGD(model.parameters(), lr=0.1, momentum=0.9, weight_decay=5e-4, nesterov=True)
  scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=num_epochs)

  trainiter = iter(train_loader)
  train_outer_iter = iter(train_loader_outer)

  ROC_AUC = []

  for epoch in range(num_epochs):

    train_loss = 0.0
    train_acc = 0.0

    inner_loss = 0.0
    inner_acc = 0.0

    test_loss = 0.0
    test_acc = 0.0

    Actual_params = []
    for name, param in model.named_parameters():
        Actual_params.append(param.data)

    for data in train_loader_outer:

      p=0
      for name, param in model.named_parameters():
          param.data = Actual_params[p] 
          p+=1
      
      x , y, trainiter = get_val_batch(train_loader, trainiter)
      x = x.cuda()
      y = y.cuda()

      y = y.unsqueeze(1)
      y_ = model(x.float())
      loss = criterion(y_, y)

      grad = torch.autograd.grad(loss, model.parameters(), create_graph = True)
      fast_weights = list(map(lambda p: p[1] - inner_lr * p[0], zip(grad, model.parameters())))

      # REPLACE THE MODEL WITH THE NEW PARAMS
      p=0
      for name, param in model.named_parameters():
          param.data = fast_weights[p]
          p+=1

      inner_loss += loss.item()
      acc = binary_acc(y_,y)
      inner_acc += acc

      ############################################################

      x, y = data
      x = x.cuda()
      y = y.cuda()

      y = y.unsqueeze(1)
      y_ = model(x.float())
      loss = criterion(y_, y) + 0.01*loss

      batch_losses.append(loss)

      train_loss += loss.item()
      acc = binary_acc(y_,y)
      train_acc += acc


      if len(batch_losses) > meta_batch_update_factor:
          #print(i)
          # now we collected the losses on all the batches of 1 epoch lets mean them and update our model

          # REPLACE THE MODEL WITH THE ORIGINAL PARAMS AS WE WILL NOW GRADS WITH RESPECT TO ORIGINAL PARAMS
          p=0
          for name, param in model.named_parameters():
            param.data = Actual_params[p]
            p+=1

          meta_batch_loss = torch.stack(batch_losses).mean()
          model.train()
          optimizer.zero_grad()
          meta_batch_loss.backward()
          optimizer.step()
          del batch_losses

          # NOW STORE IT SO TILL WE UPDATE THE ORIGINAL PARAMS
          p=0
          for name, param in model.named_parameters():
            Actual_params[p] = param.data
            p+=1


          batch_losses = []


    p=0
    for name, param in model.named_parameters():
      param.data = Actual_params[p]
      p+=1


    y_test = []
    y_pred = []

    for data in test_loader:
      x, y = data
      x = x.cuda()
      y = y.cuda()

      y = y.unsqueeze(1)
      y_ = model(x.float())
      loss = criterion(y_, y)

      y_test.append(y)
      y_pred.append(y_)

      test_loss += loss.item()
      acc = binary_acc(y_,y)
      test_acc += acc

    y_test = torch.cat(y_test).cuda()
    y_pred = torch.cat(y_pred).cuda()
    y_pred_tag = torch.round(torch.sigmoid(y_pred))

    y_test = y_test.detach().cpu().numpy()
    y_pred_tag = y_pred_tag.detach().cpu().numpy()
    y_pred = y_pred.detach().cpu().numpy()
    
    roc_auc = roc_auc_score(y_test, y_pred)
    
    ROC_AUC.append(roc_auc)

  return ROC_AUC

def getXy(X_train, y_train, method):

  if method == 'SMOTE':
    print(method)
    X_train, y_train = SMOTE().fit_resample(X_train, y_train)

  elif method == 'BorderlineSMOTE':
    print(method)
    X_train, y_train = BorderlineSMOTE().fit_resample(X_train, y_train)

  elif method == 'SVMSMOTE':
    print(method)
    X_train, y_train = SVMSMOTE().fit_resample(X_train, y_train)
  
  elif method == 'ADASYN':
    print(method)
    X_train, y_train = ADASYN().fit_resample(X_train, y_train)

  elif method == 'RandomOverSampler':
    print(method)
    X_train, y_train = RandomOverSampler().fit_resample(X_train, y_train)

  elif method == 'RandomUnderSampler':
    print(method)
    X_train, y_train = RandomUnderSampler().fit_resample(X_train, y_train)

  elif method == 'ClusterCentroids':
    print(method)
    X_train, y_train = ClusterCentroids().fit_resample(X_train, y_train)

  elif method == 'NearMiss':
    print(method)
    X_train, y_train = NearMiss(version=1).fit_resample(X_train, y_train)

  elif method == 'AllKNN':
    print(method)
    X_train, y_train = AllKNN().fit_resample(X_train, y_train)

  elif method == 'SMOTEENN':
    print(method)
    X_train, y_train = SMOTEENN().fit_resample(X_train, y_train)

  elif method == 'Simple':
    print(method)

  else:
    print('None')

  return X_train, y_train

def prepare_data(inner_method, outer_method):
  df = pd.read_csv('loan_data.csv')
  X = df.iloc[:, :-1].drop(columns='purpose').values# extracting features
  y = df.iloc[:, -1].values # extracting labels

  sc = StandardScaler()
  X = sc.fit_transform(X)

  X_train, X_test, y_train, y_test = train_test_split(X, y, test_size = 0.2, random_state = 0)

  X_train_inner, y_train_inner =  getXy(X_train, y_train, inner_method)
  X_train_outer, y_train_outer =  getXy(X_train, y_train, outer_method)

  train_dataset = trainData(torch.FloatTensor(X_train_inner), torch.FloatTensor(y_train_inner))
  train_loader = data_utils.DataLoader(train_dataset, shuffle=True, batch_size=24)

  train_dataset_outer = trainData(torch.FloatTensor(X_train_outer), torch.FloatTensor(y_train_outer))
  train_loader_outer = data_utils.DataLoader(train_dataset_outer, shuffle=True, batch_size=16)

  test_dataset = TensorDataset( torch.FloatTensor(X_test), torch.FloatTensor(y_test) )
  test_loader = data_utils.DataLoader(test_dataset , batch_size=15, shuffle=True)

  return train_loader, train_loader_outer, test_loader

class SimpleNet(nn.Module):
    def __init__(self):
        super(SimpleNet, self).__init__()
        self.model = nn.Sequential(
            nn.Linear(12, 25),
            nn.ReLU(),
            nn.Linear(25, 1),
            )

    def forward(self, x):
        x = self.model(x)
        return x

ROC_AUC = []
methods = 'Simple,SMOTE,BorderlineSMOTE,SVMSMOTE,ADASYN,RandomOverSampler,ClusterCentroids,RandomUnderSampler,NearMiss,AllKNN,SMOTEENN'.split(',')


inner_method = 'Simple'
outer_method = 'RandomUnderSampler'

print(inner_method, outer_method)
train_loader, train_loader_outer, test_loader = prepare_data(inner_method, outer_method)  

for i in range (1):

  inner_lr, meta_batch_update_factor = 0.01, 80
  roc_auc = train(inner_lr, meta_batch_update_factor)
  ROC_AUC.append(roc_auc[len(roc_auc)-1])
  print(roc_auc[len(roc_auc)-1])
    
    
def save_dict(dict, filename):
    with open(filename, 'w') as f:
        f.write(json.dumps(dict))
    
save_dict(ROC_AUC, '2_layer_25_meta.txt')



