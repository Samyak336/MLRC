

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import os
import sys
import numpy as np
import cv2
import pandas as pd
import scipy.stats as st
# from scipy.misc import imread, imsave
from imageio import imread, imsave
from tensorflow.contrib.image import transform as images_transform
from tensorflow.contrib.image import rotate as images_rotate

import tensorflow as tf

import time
start_time = time.time()

from nets import inception_v3, inception_v4, inception_resnet_v2, resnet_v2

import random

slim = tf.contrib.slim

tf.flags.DEFINE_integer('batch_size', 4, 'How many images process at one time.') # 10 -> 4

tf.flags.DEFINE_float('max_epsilon', 16.0, 'max epsilon.')

tf.flags.DEFINE_integer('num_iter', 10, 'max iteration.')

tf.flags.DEFINE_float('momentum', 1.0, 'momentum about the model.')

### 

tf.flags.DEFINE_integer('number', 20, 'the number of images for sample')

tf.flags.DEFINE_float('beta', 3.5, 'the bound for sample.')

###

tf.flags.DEFINE_integer(
    'image_width', 299, 'Width of each input images.')

tf.flags.DEFINE_integer(
    'image_height', 299, 'Height of each input images.')

tf.flags.DEFINE_float('prob', 0.5, 'probability of using diverse inputs.')

tf.flags.DEFINE_integer('image_resize', 331, 'Height of each input images.')

tf.flags.DEFINE_string('checkpoint_path', './models','Path to checkpoint for pretained models.')

tf.flags.DEFINE_string('input_dir', './dev_data/val_rs', 'Input directory with images.')
tf.flags.DEFINE_string('output_dir', './outputs/gra_v3', 'Output directory with images.')
tf.flags.DEFINE_string('labels_path','./dev_data/val_rs.csv', 'input csv')
tf.flags.DEFINE_float('eta', 0.94, 'Value for the eta parameter.')  # Set a default value
##########
tf.flags.DEFINE_float('gamma', 0.01,'Value for the gamma parameter.')
tf.flags.DEFINE_float('high_thresh', 0.75,'Value for the high_threshold for alpha parameter.')
tf.flags.DEFINE_float('low_thresh', 0.25,'Value for the low_threshold for alpha parameter.')
##########
FLAGS = tf.flags.FLAGS

# Ensure directories are passed and not None
if FLAGS.input_dir is None or FLAGS.output_dir is None or FLAGS.labels_path is None :
    raise ValueError("Both input_dir and output_dir must be specified.")

np.random.seed(0)
tf.set_random_seed(0)
random.seed(0)

model_checkpoint_map = {
    'inception_v3': os.path.join(FLAGS.checkpoint_path, 'inception_v3.ckpt'),
    'adv_inception_v3': os.path.join(FLAGS.checkpoint_path, 'adv_inception_v3_rename.ckpt'),
    'ens3_adv_inception_v3': os.path.join(FLAGS.checkpoint_path, 'ens3_adv_inception_v3_rename.ckpt'),
    'ens4_adv_inception_v3': os.path.join(FLAGS.checkpoint_path, 'ens4_adv_inception_v3_rename.ckpt'),
    'inception_v4': os.path.join(FLAGS.checkpoint_path, 'inception_v4.ckpt'),
    'inception_resnet_v2': os.path.join(FLAGS.checkpoint_path, 'inception_resnet_v2_2016_08_30.ckpt'),
    'ens_adv_inception_resnet_v2': os.path.join(FLAGS.checkpoint_path, 'ens_adv_inception_resnet_v2_rename.ckpt'),
    'resnet_v2': os.path.join(FLAGS.checkpoint_path, 'resnet_v2_101.ckpt')}


def gkern(kernlen=21, nsig=3):
    """Returns a 2D Gaussian kernel array."""
    x = np.linspace(-nsig, nsig, kernlen)
    kern1d = st.norm.pdf(x)
    kernel_raw = np.outer(kern1d, kern1d)
    kernel = kernel_raw / kernel_raw.sum()
    return kernel


kernel = gkern(7, 3).astype(np.float32)
stack_kernel = np.stack([kernel, kernel, kernel]).swapaxes(2, 0)
stack_kernel = np.expand_dims(stack_kernel, 3)


def load_images(input_dir, batch_shape):
    """Read png images from input directory in batches.
    Args:
      input_dir: input directory
      batch_shape: shape of minibatch array, i.e. [batch_size, height, width, 3]
    Yields:
      filenames: list file names without path of each image
        Lenght of this list could be less than batch_size, in this case only
        first few images of the result are elements of the minibatch.
      images: array with all images from this batch
    """
    images = np.zeros(batch_shape)
    filenames = []
    idx = 0
    batch_size = batch_shape[0]
    for filepath in tf.gfile.Glob(os.path.join(input_dir, '*')):
        with tf.gfile.Open(filepath, 'rb') as f:
            image = imread(f, pilmode='RGB').astype(np.float) / 255.0
        # Images for inception classifier are normalized to be in [-1, 1] interval.
        images[idx, :, :, :] = image * 2.0 - 1.0
        filenames.append(os.path.basename(filepath))
        idx += 1
        if idx == batch_size:
            yield filenames, images
            filenames = []
            images = np.zeros(batch_shape)
            idx = 0
    if idx > 0:
        yield filenames, images


def save_images(images, filenames, output_dir):
    """Saves images to the output directory.

    Args:
        images: array with minibatch of images
        filenames: list of filenames without path
            If number of file names in this list less than number of images in
            the minibatch then only first len(filenames) images will be saved.
        output_dir: directory where to save images
    """
    for i, filename in enumerate(filenames):
        # Images for inception classifier are normalized to be in [-1, 1] interval,
        # so rescale them back to [0, 1].
        with tf.gfile.Open(os.path.join(output_dir, filename), 'w') as f:
            imsave(f, (images[i, :, :, :] + 1.0) * 0.5, format='png')


def check_or_create_dir(directory):
    """Check if directory exists otherwise create it."""
    if not os.path.exists(directory):
        os.makedirs(directory)

def grad_finish(x, one_hot, i, max_iter, alpha, grad):
    return tf.less(i, max_iter)


def batch_grad(x, one_hot, i, max_iter, alpha, grad):
    x_neighbor = x + tf.random.uniform(x.shape, minval=-alpha, maxval=alpha)
    with slim.arg_scope(inception_v3.inception_v3_arg_scope()):
        logits_v3, end_points_v3 = inception_v3.inception_v3(
            x_neighbor, num_classes=1001, is_training=False, reuse=tf.AUTO_REUSE)
        cross_entropy = tf.losses.softmax_cross_entropy(one_hot, logits_v3)
        grad += tf.gradients(cross_entropy, x_neighbor)[0]
    i = tf.add(i, 1)
    return x, one_hot, i, max_iter, alpha, grad


############ ( Use this code for dynamic alpha ablation)
def adjust_alpha_tensor(cos_sim, alpha, gamma, high_thresh, low_thresh):
    """Dynamically adjusts alpha based on the cosine similarity."""
    mean_sim = tf.reduce_mean(cos_sim)
    adjustment_factor = tf.cond(
        mean_sim > high_thresh,
        lambda: 1 + gamma,  # Increase alpha
        lambda: tf.cond(
            mean_sim < low_thresh,
            lambda: 1 - gamma,  # Decrease alpha
            lambda: 1.0         # No change
        )
    )
    return alpha * adjustment_factor
#############


def graph(x, y, i, x_max, x_min, grad, samgrad, m): 
    eps = 2.0 * FLAGS.max_epsilon / 255.0
    num_iter = FLAGS.num_iter
    alpha= eps / num_iter
##########( Use this code for dynamic alpha ablation)
    gamma = FLAGS.gamma
    high_thresh = FLAGS.high_thresh
    low_thresh = FLAGS.low_thresh
##########
    momentum = FLAGS.momentum
    num_classes = 1001
    with slim.arg_scope(inception_v3.inception_v3_arg_scope()):
        logits_v3, end_points_v3 = inception_v3.inception_v3(
            x, num_classes=num_classes, is_training=False, reuse=tf.AUTO_REUSE)
    pred = tf.argmax(end_points_v3['Predictions'], 1)
    first_round = tf.cast(tf.equal(i, 0), tf.int64)
    y = first_round * pred + (1 - first_round) * y
    one_hot = tf.one_hot(y, num_classes)
    cross_entropy = tf.losses.softmax_cross_entropy(one_hot, logits_v3)
    new_grad = tf.gradients(cross_entropy, x)[0]
    iter = tf.constant(0)
    max_iter = tf.constant(FLAGS.number)
    _, _, _, _, _, global_grad = tf.while_loop(grad_finish, batch_grad, [x, one_hot, iter, max_iter, eps*FLAGS.beta, tf.zeros_like(new_grad)])
    samgrad = global_grad / (1. * FLAGS.number) 

############ ( Use this code for ablation 2)
    # current_grad = samgrad 
############
    ## Neighbor Weighted Correction ##    
    cossim = tf.reduce_sum(new_grad * samgrad, [1, 2, 3]) / (tf.sqrt(tf.reduce_sum(new_grad ** 2, [1, 2, 3])) * tf.sqrt(tf.reduce_sum(samgrad ** 2, [1, 2, 3])))
    cossim = tf.expand_dims(cossim, -1)
    cossim = tf.expand_dims(cossim, -1)
    cossim = tf.expand_dims(cossim, -1)
    # cossim=tf.maximum(low,cossim)
    current_grad = cossim*new_grad + (1-cossim)*samgrad  
########### ( Use this code for dynamic alpha ablation)
    alpha = adjust_alpha_tensor(tf.reduce_mean(cossim), eps / num_iter, gamma, high_thresh, low_thresh)
###########
    noiselast = grad
    noise = momentum * grad + (current_grad) / tf.reduce_mean(tf.abs(current_grad), [1, 2, 3], keep_dims=True)
    eqm = tf.cast(tf.equal(tf.sign(noiselast), tf.sign(noise)), dtype = tf.float32)    
    dim = tf.ones( x.shape ) - eqm
    # Use FLAGS.eta in the code where `eta` is defined:
    eta = FLAGS.eta  # Use this in your 'graph' function or wherever `eta` is used
    m = m * ( eqm + dim * eta )                          
    x = x + alpha * m * tf.sign(noise)
    x = tf.clip_by_value(x, x_min, x_max)
    i = tf.add(i, 1)
    return x, y, i, x_max, x_min, noise, samgrad, m


def stop(x, y, i, x_max, x_min, grad, samgrad, m):
    num_iter = FLAGS.num_iter
    return tf.less(i, num_iter)

############################################### (Use this code for GRA-CT)
# def image_augmentation(x):
#     # img, noise
#     one = tf.fill([tf.shape(x)[0], 1], 1.)
#     zero = tf.fill([tf.shape(x)[0], 1], 0.)
#     transforms = tf.concat([one, zero, zero, zero, one, zero, zero, zero], axis=1)
#     rands = tf.concat([tf.truncated_normal([tf.shape(x)[0], 6], stddev=0.05), zero, zero], axis=1)
#     return images_transform(x, transforms + rands, interpolation='BILINEAR')


# def image_rotation(x):
#     """ imgs, scale, scale is in radians """
#     rands = tf.truncated_normal([tf.shape(x)[0]], stddev=0.05)
#     return images_rotate(x, rands, interpolation='BILINEAR')


# def input_diversity(input_tensor):
#     rnd = tf.random_uniform((), FLAGS.image_width, FLAGS.image_resize, dtype=tf.int32)
#     rescaled = tf.image.resize_images(input_tensor, [rnd, rnd], method=tf.image.ResizeMethod.NEAREST_NEIGHBOR)
#     h_rem = FLAGS.image_resize - rnd
#     w_rem = FLAGS.image_resize - rnd
#     pad_top = tf.random_uniform((), 0, h_rem, dtype=tf.int32)
#     pad_bottom = h_rem - pad_top
#     pad_left = tf.random_uniform((), 0, w_rem, dtype=tf.int32)
#     pad_right = w_rem - pad_left
#     padded = tf.pad(rescaled, [[0, 0], [pad_top, pad_bottom], [pad_left, pad_right], [0, 0]], constant_values=0.)
#     padded.set_shape((input_tensor.shape[0], FLAGS.image_resize, FLAGS.image_resize, 3))
#     ret = tf.cond(tf.random_uniform(shape=[1])[0] < tf.constant(FLAGS.prob), lambda: padded, lambda: input_tensor)
#     ret = tf.image.resize_images(ret, [FLAGS.image_height, FLAGS.image_width],
#                                  method=tf.image.ResizeMethod.NEAREST_NEIGHBOR)
#     return ret
    ## return tf.cond(tf.random_uniform(shape=[1])[0] < tf.constant(FLAGS.prob), lambda: padded, lambda: input_tensor)
###############################################

def main(_):
    # Images for inception classifier are normalized to be in [-1, 1] interval,
    # eps is a difference between pixels so it should be in [0, 2] interval.
    # Renormalizing epsilon from [0, 255] to [0, 2].
    f2l = load_labels(FLAGS.labels_path)
    eps = 2 * FLAGS.max_epsilon / 255.0

    batch_shape = [FLAGS.batch_size, FLAGS.image_height, FLAGS.image_width, 3]

    tf.logging.set_verbosity(tf.logging.INFO)

    check_or_create_dir(FLAGS.output_dir)
    print(time.time() - start_time)

    with tf.Graph().as_default():
        # Prepare graph
        x_input = tf.placeholder(tf.float32, shape=batch_shape)
        x_max = tf.clip_by_value(x_input + eps, -1.0, 1.0)
        x_min = tf.clip_by_value(x_input - eps, -1.0, 1.0)

        y = tf.constant(np.zeros([FLAGS.batch_size]), tf.int64)
        i = tf.constant(0)

        x_adv, _, _, _, _, _, _, _ = tf.while_loop(stop, graph, [x_input, y, i, x_max, x_min, tf.zeros(shape=batch_shape), tf.zeros(shape=batch_shape), tf.ones(shape=batch_shape)*10.0/9.4])

        # Run computation
        s1 = tf.train.Saver(slim.get_model_variables(scope='InceptionV3'))
        # s2 = tf.train.Saver(slim.get_model_variables(scope='InceptionV4'))
        # s3 = tf.train.Saver(slim.get_model_variables(scope='InceptionResnetV2'))
        # s4 = tf.train.Saver(slim.get_model_variables(scope='resnet_v2'))
        # s5 = tf.train.Saver(slim.get_model_variables(scope='Ens3AdvInceptionV3'))
        # s6 = tf.train.Saver(slim.get_model_variables(scope='Ens4AdvInceptionV3'))
        # s7 = tf.train.Saver(slim.get_model_variables(scope='EnsAdvInceptionResnetV2'))
        # s8 = tf.train.Saver(slim.get_model_variables(scope='AdvInceptionV3'))
        print(time.time() - start_time)

        with tf.Session(config=tf.ConfigProto(allow_soft_placement=True)) as sess:
            s1.restore(sess, model_checkpoint_map['inception_v3'])
            # s2.restore(sess, model_checkpoint_map['inception_v4'])
            # s3.restore(sess, model_checkpoint_map['inception_resnet_v2'])
            # s4.restore(sess, model_checkpoint_map['resnet_v2'])
            # s5.restore(sess, model_checkpoint_map['ens3_adv_inception_v3'])
            # s6.restore(sess, model_checkpoint_map['ens4_adv_inception_v3'])
            # s7.restore(sess, model_checkpoint_map['ens_adv_inception_resnet_v2'])
            # s8.restore(sess, model_checkpoint_map['adv_inception_v3'])

            idx = 0
            l2_diff = 0
            for filenames, images in load_images(FLAGS.input_dir, batch_shape):
                idx = idx + 1
                print("start the i={} attack".format(idx))
########################################## (Use this code for GRA-CT)
                # # Convert images to a tensor
                # images_tensor = tf.convert_to_tensor(images, dtype=tf.float32)
                
                # # Apply augmentation
                # images_tensor = image_augmentation(images_tensor)
                # images_tensor = image_rotation(images_tensor)
                # images_tensor = input_diversity(images_tensor)
                # adv_images = sess.run(x_adv, feed_dict={x_input: images_tensor.eval()})
##########################################        

                adv_images = sess.run(x_adv, feed_dict={x_input: images})
                save_images(adv_images, filenames, FLAGS.output_dir)
                diff = (adv_images + 1) / 2 * 255 - (images + 1) / 2 * 255
                l2_diff += np.mean(np.linalg.norm(np.reshape(diff, [-1, 3]), axis=1))
                # break

            print('{:.2f}'.format(l2_diff * FLAGS.batch_size / 1000))
            print(time.time() - start_time)
        print(time.time() - start_time)
        
def load_labels(file_name):
    import pandas as pd
    dev = pd.read_csv(file_name)
    f2l = {dev.iloc[i]['filename']: dev.iloc[i]['label'] for i in range(len(dev))}
    return f2l


if __name__ == '__main__':
    tf.app.run()























