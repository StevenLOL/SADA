from math import pi
from numpy import *
import os
import matplotlib.pyplot as plt
#from pylab import *
import numpy as np
from sklearn import cluster
from sklearn.neighbors import NearestNeighbors
from scipy.spatial import distance
import sklearn.datasets
from sklearn.preprocessing import StandardScaler
#import matplotlib.pyplot as plt
#import matplotlib.cbook as cbook
import time
import sys
import scipy.io as sio
from scipy import ndimage , misc
from scipy import stats
import matplotlib.image as mpimg
from scipy.ndimage import filters
import urllib
import math
import numpy as np 
import tensorflow as tf

from tensorflow.python.framework import ops

from utils import *

from sklearn import mixture


def function_batches(function, input_list=range(1000), slice_size=100):
    full_output = []
    x_batches = [input_list[ii:ii+slice_size]
                 for ii in range(0, len(input_list), slice_size)]
    # if len(input_list) % self.slice_size != 0 :
    #     x_batches.pop()
    for ii in range(len(x_batches)):
        full_output.append(function(x_batches[ii]))
    return full_output
# a function that applies the function in the argument ( which accepts athe list of inputs ) as batches and returen a list of batched output 7


def black_box(input_vector, output_size=256, global_step=0, frames_path=None, cluster=False, parent_name='car', scenario_nb=0):
    b = Blender(cluster, 'init.py', '3d/training_pascal/training.blend')
    b.city_experiment(obj_name="myorigin", vec=np.array(
        input_vector).tolist(), parent_name=parent_name, scenario_nb=scenario_nb)
    b.save_image(output_size, output_size,
                 path=frames_path, name=str(global_step))
    # b.save_file()
    b.execute()
    image = cv2.imread(os.path.join(frames_path, str(global_step)+".jpg"))
    image = forward_transform(cv2.cvtColor(
        image, cv2.COLOR_BGR2RGB).astype(np.float32))
    return image


def black_box_batch(input_vectors, output_size=256, global_step=0, frames_path=None, cluster=False, parent_name='car', scenario_nb=0):
    images = []
    for input_vector in input_vectors:
        try:
            images.append(black_box(np.array(input_vector), output_size,
                                    global_step, frames_path, cluster, parent_name, scenario_nb))
            # images.append(black_box(np.array(input_vector),output_size,len(images),frames_path,cluster,parent_name,scenario_nb))

        except:
            continue
    # print("&&&&&&&&&&&&&&&&&&&&&\n\n",np.linalg.norm(np.mean(np.array(images) - np.broadcast_to(np.mean(np.array(images),axis=0),np.array(images).shape),axis=2),ord="fro"))
    return images


def normalize_vectors_list(vector_list, old_max, old_min, new_max, new_min):
    old_range = old_max - old_min
    new_range = new_max - new_min
    range_ratio = new_range / old_range
    matrix = np.array(vector_list)
    matrix = np.broadcast_to(new_min, matrix.shape) + (matrix - np.broadcast_to(
        old_min, matrix.shape)) * np.broadcast_to(range_ratio, matrix.shape)
    return list(matrix)



def sample_from_learned_gaussian(points_to_learn, n_components=1, n_samples=10, is_truncate=True, is_reject=False, min_value=-1, max_value=1):
    gmm = mixture.GaussianMixture(
        n_components=n_components, covariance_type='full', max_iter=50000).fit(points_to_learn)
    if is_truncate:
        return np.clip(gmm.sample(n_samples=n_samples)[0], min_value, max_value)
    elif is_reject:
        sample_list = []
        MAX_ITER = 100000000
        iteration = 0
        a = list(gmm.sample(n_samples=100*n_samples)[0])
        while len(sample_list) < n_samples and iteration < MAX_ITER:
            if (a[iteration] >= min_value).all() and (a[iteration] <= max_value).all():
                sample_list.append(a[iteration])
            iteration += 1
        return np.array(sample_list)
    else:
        # , gmm.means_, gmm.covariances
        return gmm.sample(n_samples=n_samples)[0]



try:
  image_summary = tf.image_summary
  scalar_summary = tf.scalar_summary
  histogram_summary = tf.histogram_summary
  merge_summary = tf.merge_summary
  SummaryWriter = tf.train.SummaryWriter
except:
  image_summary = tf.summary.image
  scalar_summary = tf.summary.scalar
  histogram_summary = tf.summary.histogram
  merge_summary = tf.summary.merge
  SummaryWriter = tf.summary.FileWriter

if "concat_v2" in dir(tf):
  def concat(tensors, axis, *args, **kwargs):
    return tf.concat_v2(tensors, axis, *args, **kwargs)
else:
  def concat(tensors, axis, *args, **kwargs):
    return tf.concat(tensors, axis, *args, **kwargs)

class batch_norm(object):
  def __init__(self, epsilon=1e-5, momentum = 0.9, name="batch_norm"):
    with tf.variable_scope(name):
      self.epsilon  = epsilon
      self.momentum = momentum
      self.name = name

  def __call__(self, x, train=True):
    return tf.contrib.layers.batch_norm(x,
                      decay=self.momentum, 
                      updates_collections=None,
                      epsilon=self.epsilon,
                      scale=True,
                      is_training=train,
                      scope=self.name)

def conv_cond_concat(x, y):
  """Concatenate conditioning vector on feature map axis."""
  x_shapes = x.get_shape()
  y_shapes = y.get_shape()
  return concat([
    x, y*tf.ones([x_shapes[0], x_shapes[1], x_shapes[2], y_shapes[3]])], 3)

def conv2d(input_, output_dim, 
       k_h=5, k_w=5, d_h=2, d_w=2, stddev=0.02,
       name="conv2d"):
  with tf.variable_scope(name):
    w = tf.get_variable('w', [k_h, k_w, input_.get_shape()[-1], output_dim],
              initializer=tf.truncated_normal_initializer(stddev=stddev))
    conv = tf.nn.conv2d(input_, w, strides=[1, d_h, d_w, 1], padding='SAME')

    biases = tf.get_variable('biases', [output_dim], initializer=tf.constant_initializer(0.0))
    conv = tf.reshape(tf.nn.bias_add(conv, biases), conv.get_shape())

    return conv

def deconv2d(input_, output_shape,
       k_h=5, k_w=5, d_h=2, d_w=2, stddev=0.02,
       name="deconv2d", with_w=False):
  with tf.variable_scope(name):
    # filter : [height, width, output_channels, in_channels]
    w = tf.get_variable('w', [k_h, k_w, output_shape[-1], input_.get_shape()[-1]],
              initializer=tf.random_normal_initializer(stddev=stddev))
    
    try:
      deconv = tf.nn.conv2d_transpose(input_, w, output_shape=output_shape,
                strides=[1, d_h, d_w, 1])

    # Support for verisons of TensorFlow before 0.7.0
    except AttributeError:
      deconv = tf.nn.deconv2d(input_, w, output_shape=output_shape,
                strides=[1, d_h, d_w, 1])

    biases = tf.get_variable('biases', [output_shape[-1]], initializer=tf.constant_initializer(0.0))
    deconv = tf.reshape(tf.nn.bias_add(deconv, biases), deconv.get_shape())

    if with_w:
      return deconv, w, biases
    else:
      return deconv
     
def lrelu(x, leak=0.2, name="lrelu"):
  return tf.maximum(x, leak*x)

def linear(input_, output_size, scope=None, stddev=0.02, bias_start=0.0, with_w=False):
  shape = input_.get_shape().as_list()

  with tf.variable_scope(scope or "Linear"):
    matrix = tf.get_variable("Matrix", [shape[1], output_size], tf.float32,
                 tf.random_normal_initializer(stddev=stddev))
    bias = tf.get_variable("bias", [output_size],
      initializer=tf.constant_initializer(bias_start))
    if with_w:
      return tf.matmul(input_, matrix) + bias, matrix, bias
    else:
      return tf.matmul(input_, matrix) + bias

def conv(input, kernel, biases, k_h, k_w, c_o, s_h, s_w,  padding="VALID", group=1):
    '''From https://github.com/ethereon/caffe-tensorflow
    '''
    c_i = input.get_shape()[-1]
    assert c_i%group==0
    assert c_o%group==0
    convolve = lambda i, k: tf.nn.conv2d(i, k, [1, s_h, s_w, 1], padding=padding)
    
    
    if group==1:
        conv = convolve(input, kernel)
    else:
        input_groups =  tf.split(input, group, 3)   #tf.split(3, group, input)
        kernel_groups = tf.split(kernel, group, 3)  #tf.split(3, group, kernel) 
        output_groups = [convolve(i, k) for i,k in zip(input_groups, kernel_groups)]
        conv = tf.concat(output_groups, 3)          #tf.concat(3, output_groups)
    return  tf.reshape(tf.nn.bias_add(conv, biases), [-1]+conv.get_shape().as_list()[1:])

def mysigmoid(x,mean=0,bw=1):
  return 1 / (1 + np.exp(-(x-mean)/bw))
def sigmoid_hamming(x,mean=0,bw=1,boundary=14000):
  z = np.hanning(boundary)
  zz= 1 / (1 + np.exp(-(x-mean)/bw))
  return 5*z[x] *zz 
def square_signal(x,bw=20,duty=0.5):
  kk = np.mod(x,bw) < duty*bw
  return kk.astype(int)

