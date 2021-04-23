
# coding: utf-8

# In[1]:
from __future__ import print_function

import os
# os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
# os.environ["CUDA_VISIBLE_DEVICES"] = "2"


# In[2]:




import os
import sys
import numpy as np
from keras.preprocessing.text import Tokenizer
from keras.preprocessing.sequence import pad_sequences
from keras.utils import to_categorical
from keras.layers import Dense, Input, GlobalMaxPooling1D, Dropout, concatenate
from keras.layers import Conv1D, MaxPooling1D, Embedding, Bidirectional, LSTM
from keras.models import Model
from models.custom_metrics import hamming_score, f1
from keras import optimizers, regularizers
from keras.callbacks import EarlyStopping
# import matplotlib.pyplot as plt
import logging, pickle



# In[3]:
# conv_units = int(sys.argv[1])
# filter_size = 3
# pooling_size = 3
# dropout_rate = float(sys.argv[2])
# dense_units = int(sys.argv[3])
# max_len = int(sys.argv[4])

conv_units = 1024 #int(sys.argv[1])
filter_size = 3
pooling_size = 3
dropout_rate = 0.6 #float(sys.argv[2])
dense_units = 256 #int(sys.argv[3])
max_len = 800 #int(sys.argv[4])

logging.basicConfig(filename='../res/cnn_feature/{}_{}_{}_{}.log'.format(conv_units, dropout_rate, dense_units, max_len), level=logging.INFO)

BASE_DIR = ''
GLOVE_DIR = '../data/'
# EMBEDDING_FILE = 'glove.6B.100d.txt'
EMBEDDING_FILE = 'glove.6B.100d.txt'
MAX_SEQUENCE_LENGTH = max_len
MAX_NUM_WORDS = 20000
EMBEDDING_DIM = 100
EMBED_INIT_GLOVE = True
FEAT_NUM = 24


# In[4]:


train_file = '../data/issuedialog/train.tsv'
valid_file = '../data/issuedialog/valid.tsv'
test_file = '../data/issuedialog/test.tsv'

train_feat_file = '../data/issuedialog/train_features.tsv'
valid_feat_file = '../data/issuedialog/valid_features.tsv'
test_feat_file = '../data/issuedialog/test_features.tsv'


# In[5]:


# first, build index mapping words in the embeddings set to their embedding vector

print('Indexing word vectors.')

embeddings_index = {}
with open(os.path.join(GLOVE_DIR, EMBEDDING_FILE), encoding='utf8') as f:
    for line in f:
        values = line.split(' ')
        word = values[0]
        coefs = np.asarray(values[1:], dtype='float32')
        embeddings_index[word] = coefs

print('Found %s word vectors.' % len(embeddings_index))


# In[6]:


# second, prepare text samples and their labels
print('Processing text dataset')

texts = []  # list of text samples
# labels_index = {'OQ': 0, 'OP': 1, 'OF': 2, 'FD': 3, 'FQ': 4, 'CQ': 5, 'AE': 6, 'AC': 7, 'IG': 8, 'CC': 9, 'UF': 10,
#                 'PF': 11, 'NF': 12, 'GG': 13, 'JK': 14}
labels_index = {'0': 0, '1': 1}
id2label = {v: k for k, v in labels_index.items()}
classes_num = len(labels_index)

def load_data_and_labels(data_file):
    x = []
    y = []
    i = 0
    with open(data_file, encoding='utf8') as raw_data:
        for line in raw_data:
            i += 1
#             print(i)
            if line != '\n':
                line = line.strip()
                tokens = line.split('\t')
                labels = tokens[3].split('_')
                x.append(tokens[1])
                each_y = [0] * classes_num
                for label in labels:
                    each_y[labels_index[label]] = 1
                y.append(each_y)
    return x, y

x_train, y_train = load_data_and_labels(train_file)
x_valid, y_valid = load_data_and_labels(valid_file)
x_test, y_test = load_data_and_labels(test_file)


# MAX_SEQUENCE_LENGTH = max(max(map(len, x_train)), max(map(len, x_valid)), max(map(len, x_test)))
# print(MAX_SEQUENCE_LENGTH)

labels = np.array(y_train + y_valid + y_test)

print('Found %s texts.' % len(x_train + x_valid + x_test))


# In[7]:


def load_features(data_file):
    x = []
    i = 0
    with open(data_file, encoding='utf8') as raw_data:
        for line in raw_data:
            i += 1
#             print(i)
            if line != '\n':
                line = line.strip()
                tokens = line.split('\t')
                features = list(map(float, tokens[1].split()))
                x.append(features)
    return np.array(x)

x_train_feat = load_features(train_feat_file)
x_val_feat = load_features(valid_feat_file)
x_test_feat = load_features(test_feat_file)

print('Found %s features.' % len(x_train_feat[0]))


# In[8]:


# finally, vectorize the text samples into a 2D integer tensor
tokenizer = Tokenizer(num_words=MAX_NUM_WORDS)
tokenizer.fit_on_texts(x_train + x_valid)
sequences = tokenizer.texts_to_sequences(x_train + x_valid + x_test)

word_index = tokenizer.word_index
print('Found %s unique tokens.' % len(word_index))

data = pad_sequences(sequences, maxlen=MAX_SEQUENCE_LENGTH)

# labels = to_categorical(np.asarray(y_train))
print('Shape of data tensor:', data.shape)
print('Shape of label tensor:', labels.shape)
print('Shape of feature tensor:', x_train_feat.shape)


# In[9]:


print('Preparing embedding matrix.')

# prepare embedding matrix
num_words = min(MAX_NUM_WORDS, len(word_index) + 1)

if EMBED_INIT_GLOVE:
    embedding_matrix = np.zeros((num_words, EMBEDDING_DIM))
    for word, i in word_index.items():
        if i >= MAX_NUM_WORDS:
            continue
        embedding_vector = embeddings_index.get(word)
        if embedding_vector is not None:
            # words not found in embedding index will be all-zeros.
            embedding_matrix[i] = embedding_vector

    # load pre-trained word embeddings into an Embedding layer
    # note that we set trainable = False so as to keep the embeddings fixed
    embedding_layer = Embedding(num_words,
                                EMBEDDING_DIM,
                                weights=[embedding_matrix],
                                input_length=MAX_SEQUENCE_LENGTH,
                                trainable=True)
else:
    embedding_layer = Embedding(num_words, 
                                EMBEDDING_DIM, 
                                embeddings_initializer='uniform', 
                                input_length=MAX_SEQUENCE_LENGTH)


# In[ ]:


num_validation_samples = len(y_valid)
num_test_samples = len(y_test)
num_train_samples = len(y_train)
num_total_samples = len(labels)

x_train = data[:num_train_samples]
y_train = labels[:num_train_samples]
x_val = data[num_train_samples: num_train_samples + num_validation_samples]
y_val = labels[num_train_samples: num_train_samples + num_validation_samples]
x_test = data[-num_test_samples:]
y_test = labels[-num_test_samples:]

assert len(x_train) + len(x_val) + len(x_test) == len(labels)
assert len(y_train) + len(y_val) + len(y_test) == len(labels)


# In[ ]:


print('Training model.')

# train a 1D convnet with global maxpooling
sequence_input = Input(shape=(MAX_SEQUENCE_LENGTH,), dtype='int32')
feature_input = Input(shape=(FEAT_NUM,), dtype='float32')
embedded_sequences = embedding_layer(sequence_input)
x = Conv1D(conv_units, filter_size, activation='relu')(embedded_sequences)
x = MaxPooling1D(pooling_size)(x)
x = Dropout(dropout_rate)(x)
x = Conv1D(conv_units, filter_size, activation='relu')(x)
x = MaxPooling1D(pooling_size)(x)
x = Dropout(dropout_rate)(x)
x = Conv1D(conv_units, filter_size, activation='relu')(x)
x = GlobalMaxPooling1D()(x)
x = Dropout(dropout_rate)(x)
x = Dense(dense_units * 2, activation='relu')(x)
x = Dropout(dropout_rate)(x)
x = Dense(dense_units, activation='relu')(x)
concat = concatenate([x, feature_input])
preds = Dense(len(labels_index), activation='sigmoid')(concat)

model = Model([sequence_input, feature_input], preds)

# adam = optimizers.Adam(lr=0.001, beta_1=0.9, beta_2=0.999, epsilon=None, decay=0.0, amsgrad=False)

model.compile(loss='binary_crossentropy',
              optimizer='adam',
              metrics=['binary_accuracy'])

es = EarlyStopping(monitor='val_loss',
                  min_delta=0,
                  patience=2,
                  verbose=0, mode='auto')

history = model.fit([x_train, x_train_feat], y_train,
          batch_size=16,
          epochs=100,
          callbacks=[es],
          validation_data=([x_val, x_val_feat], y_val))

model.save_weights('weights_cnn_feature_pa&-pa.h5',overwrite=True)

# In[ ]:


# plt.plot(history.history['loss'])
# plt.plot(history.history['val_loss'])
# plt.title('model loss')
# plt.ylabel('loss')
# plt.xlabel('epoch')
# plt.legend(['train', 'val'], loc='upper left')
# plt.show()

from copy import deepcopy
model.load_weights('weights_cnn_feature_pa&-pa.h5')
pred_val = model.predict([np.array(x_val), x_val_feat])
pred_test = model.predict([np.array(x_test), x_test_feat])

# In[ ]:

for th in [0.2, 0.3, 0.4, 0.5, 0.6, 0.7]:
    pred = deepcopy(pred_val)

    # if predicted proba >= 0.5, this label is set to 1. if all probas < 0.5, the label with largest proba is set to 1
    for i in range(pred.shape[0]):
        if len(np.where(pred[i] >= th)[0]) > 0:
            pred[i][pred[i] >= th] = 1
            pred[i][pred[i] < th] = 0
        else:
            max_index = np.argmax(pred[i])
            pred[i] = 0
            pred[i][max_index] = 1

    # In[ ]:

    acc_val = hamming_score(y_val, pred)
    p_val, r_val, f1_val = f1(y_val, pred)
    print('Eval====>Th: {}, Acc: {}, P: {}, R: {}, F1: {}'.format(th, acc_val, p_val, r_val, f1_val))

    # In[ ]:

    pred = deepcopy(pred_test)

    for i in range(pred.shape[0]):
        if len(np.where(pred[i] >= th)[0]) > 0:
            pred[i][pred[i] >= th] = 1
            pred[i][pred[i] < th] = 0
        else:
            max_index = np.argmax(pred[i])
            pred[i] = 0
            pred[i][max_index] = 1
    acc_test = hamming_score(y_test, pred)
    p_test, r_test, f1_test = f1(y_test, pred)
    print('Test====>Th: {}, Acc: {}, P: {}, R: {}, F1: {}'.format(th, acc_test, p_test, r_test, f1_test))

    # logging
    # pickle_name = '../res/cnn_context_rep_gitter/{}_{}_{}_{}_{}_{}_{}.res'.format(conv_units, dropout_rate, dense_units, max_len,  context_conv_units, context_dense_units, th)
    # pickle_file = open(pickle_name, 'wb')
    # pickle.dump(pred, pickle_file, pickle.HIGHEST_PROTOCOL)
    # pickle_file.close()
    #
    # logging.info('{},{},{},{},{},{},{},{},{},{},{},{},{},{},{}'.format(
    #     conv_units, dropout_rate, dense_units, max_len, context_conv_units, context_dense_units, th, acc_val, p_val, r_val, f1_val, acc_test, p_test, r_test, f1_test
    # ))