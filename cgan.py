from __future__ import print_function, division

from keras.datasets import mnist
from keras.layers import Input, Dense, Reshape, Flatten, Dropout
from keras.layers import BatchNormalization, Activation, ZeroPadding2D, Embedding, Multiply
from keras.layers.advanced_activations import LeakyReLU
from keras.layers.convolutional import UpSampling2D, Conv2D
from keras.models import Sequential, Model
from keras.optimizers import Adam
import cv2

import matplotlib.pyplot as plt

import sys

import numpy as np


class CGAN():
    def __init__(self):
        # Input shape
        self.img_rows = 128
        self.img_cols = 128
        self.channels = 1
        self.img_shape = (self.img_rows, self.img_cols, self.channels)
        self.num_classes = 5
        self.latent_dim = 10000

        optimizer = Adam(0.0002, 0.5)

        # Build and compile the discriminator
        self.discriminator = self.build_discriminator()
        self.discriminator.compile(loss='binary_crossentropy',
                                   optimizer=optimizer,
                                   metrics=['accuracy'])

        # Build the generator
        self.generator = self.build_generator()

        # The generator takes noise as input and generates imgs
        noise = Input(shape=(self.latent_dim,))
        label = Input(shape=(1,))

        img = self.generator([noise, label])
        # For the combined model we will only train the generator
        self.discriminator.trainable = False

        # The discriminator takes generated images as input and determines validity
        valid = self.discriminator([img, label])

        # The combined model  (stacked generator and discriminator)
        # Trains the generator to fool the discriminator
        self.combined = Model([noise, label], valid)
        self.combined.compile(loss='binary_crossentropy', optimizer=optimizer)

    def build_generator(self):

        model = Sequential()
        model.add(Dense(256, input_dim=self.latent_dim))
        model.add(LeakyReLU(alpha=0.2))
        model.add(BatchNormalization(momentum=0.8))
        model.add(Dense(512))
        model.add(LeakyReLU(alpha=0.2))
        model.add(BatchNormalization(momentum=0.8))
        model.add(Dense(1024))
        model.add(LeakyReLU(alpha=0.2))
        model.add(BatchNormalization(momentum=0.8))
        model.add(Dense(np.prod(self.img_shape), activation='tanh'))
        model.add(Reshape(self.img_shape))

        model.summary()

        noise = Input(shape=(self.latent_dim,))
        label = Input(shape=(1,), dtype='int32')
        label_embedding = Flatten()(Embedding(self.num_classes, self.latent_dim)(label))

        model_input = Multiply([noise, label_embedding])
        img = model(model_input)

        return Model([noise, label], img)

    def build_discriminator(self):

        model = Sequential()

        model.add(Dense(512, input_dim=np.prod(self.img_shape)))
        model.add(LeakyReLU(alpha=0.2))
        model.add(Dense(512))
        model.add(LeakyReLU(alpha=0.2))
        model.add(Dropout(0.4))
        model.add(Dense(512))
        model.add(LeakyReLU(alpha=0.2))
        model.add(Dropout(0.4))
        model.add(Dense(1, activation='sigmoid'))
        model.summary()

        img = Input(shape=self.img_shape)
        label = Input(shape=(1,), dtype='int32')

        label_embedding = Flatten()(Embedding(self.num_classes, np.prod(self.img_shape))(label))
        flat_img = Flatten()(img)

        model_input = Multiply([flat_img, label_embedding])

        validity = model(model_input)

        return Model([img, label], validity)

    def load_xrays(self, epochs=10, batch_size=128, save_interval=1):
        (img_x, img_y) = 128, 128
        train_path = "/Desktop/newDataTrain.csv"

        classes = ['Atelectasis', 'No Finding', 'Cardiomegaly', 'Effusion', 'Pneumothorax']
        num_classes = len(classes)

        # Load training data
        dataTrain = pd.read_csv(train_path)

        x_train = []
        y_train = []
        # prepare label binarizer
        from sklearn import preprocessing
        lb = preprocessing.LabelBinarizer()

        for index, row in dataTrain.iterrows():
            img1 = row["File Name"]
            image1 = cv2.imread(img1)  # Image.open(img).convert('L')
            image1 = image1[:, :, 0]
            arr1 = cv2.resize(image1, (img_x, img_y))
            arr1 = arr1.astype('float32')
            arr1 /= 255.0
            arr1 = arr1 - np.mean(arr1)
            x_train.append(arr1)
            # not yet one-hot encoded
            y_train.append(row["Finding Labels"])
            # OHE the y data
        y_train = lb.fit_transform(y_train)
        # finalize data
        x_train = np.asarray(x_train)
        x_train = x_train.reshape(len(dataTrain.index), img_y, img_x, 1)
        y_train = y_train.reshape(len(dataTrain.index), num_classes)

        valid = np.ones((batch_size, 1))
        fake = np.zeros((batch_size, 1))

        for epoch in range(epochs):

            # ---------------------
            #  Train Discriminator
            # ---------------------

            # Select a random half of images
            idx = np.random.randint(0, x_train.shape[0], batch_size)
            imgs, labels = x_train[idx], y_train[idx]

            # Sample noise and generate a batch of new images
            noise = np.random.normal(0, 1, (batch_size, self.latent_dim))
            gen_imgs = self.generator.predict([noise, labels])

            # Train the discriminator (real classified as ones and generated as zeros)
            d_loss_real = self.discriminator.train_on_batch([imgs, labels], valid)
            d_loss_fake = self.discriminator.train_on_batch([gen_imgs, labels], fake)
            d_loss = 0.5 * np.add(d_loss_real, d_loss_fake)

            # ---------------------
            #  Train Generator
            # ---------------------

            # Condition on labels
            sampled_labels = np.random.randint(0, 5, batch_size).reshape(-1, 1)

            # Train the generator (wants discriminator to mistake images as real)
            g_loss = self.combined.train_on_batch([noise, sampled_labels], valid)

            # Plot the progress
            print("%d [D loss: %f, acc.: %.2f%%] [G loss: %f]" % (epoch, d_loss[0], 100 * d_loss[1], g_loss))

            # If at save interval => save generated image samples
            if epoch % save_interval == 1:
                self.save_imgs(epoch)

    def save_imgs(self, epoch):
        r, c = 5,5
        noise = np.random.normal(0, 1, (r * c, self.latent_dim))
        gen_imgs = self.generator.predict(noise)

        # Rescale images 0 - 1
        gen_imgs = 0.5 * gen_imgs + 0.5

        fig, axs = plt.subplots(r, c)
        cnt = 0
        for i in range(r):
            for j in range(c):
                axs[i, j].imshow(gen_imgs[cnt, :, :, 0], cmap='gray')
                axs[i, j].axis('off')
                cnt += 1
        fig.savefig("images/mnist_%d.png" % epoch)
        plt.close()


if __name__ == '__main__':
    cgan = CGAN()
    cgan.load_xrays(epochs=10, batch_size=128, save_interval=1)
    model.save('/Desktop/cgan.h5')
    # Generate one-hot-encoded labels
    # prepare label binarizer

    from sklearn import preprocessing
    lb = preprocessing.LabelBinarizer()

    classes = ['Atelectasis', 'No Finding', 'Cardiomegaly', 'Effusion', 'Pneumothorax']

    OHE_labels = lb.fit_transform(classes)

    # at the end, loop per class, per 1000 images
    for labels in OHE_labels:
        noise1 = np.random.normal(0, 1, (1000, cgan.latent_dim))
        labels1 = np.tile(labels, 1000)
        cgan.predict([noise1, labels1])
