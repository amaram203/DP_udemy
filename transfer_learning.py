"""
Train a neural network to differentiate between TMNTs and Koopa Troopas
"""
# pylint: disable=invalid-name
import time

from keras.applications.inception_v3 import InceptionV3, preprocess_input
from keras.optimizers import SGD
from keras.preprocessing.image import ImageDataGenerator
from keras.models import Model
from keras.layers import Dense, GlobalAveragePooling2D
from keras.callbacks import LambdaCallback, ModelCheckpoint
from keras import metrics
import meeshkan


# create the base pre-trained model
base_model = InceptionV3(weights='imagenet', include_top=False)

# add a global spatial average pooling layer
x = base_model.output
x = GlobalAveragePooling2D()(x)

# let's add a fully-connected layer
x = Dense(1024, activation='relu')(x)
x = Dense(512, activation='relu')(x)
x = Dense(32, activation='relu')(x)

# and a logistic layer -- we have 2 classes - koopa troopers and tmnt
predictions = Dense(2, activation='softmax')(x)

# this is the model we will train
model = Model(inputs=base_model.input, outputs=predictions)

# first: train only the top layers (which were randomly initialized)
# i.e. freeze all convolutional InceptionV3 layers
for layer in base_model.layers:
    layer.trainable = False

# compile the model (should be done *after* setting layers to non-trainable)
model.compile(optimizer='rmsprop', loss='categorical_crossentropy', metrics=[metrics.categorical_accuracy])


# Report train set loss and categorical accuracy to the Meeshkan agent at the end of minibatch
def on_batch_end(batch, logs):  # pylint: disable=unused-argument
    try:
        meeshkan.report_scalar("Train loss", float(logs['loss']))
        meeshkan.report_scalar("Train accuracy", float(logs['categorical_accuracy']))
    except Exception as e:  # pylint: disable=broad-except
        print(e)


meeshkan_callback = LambdaCallback(on_batch_end=on_batch_end)


def _make_generator(dest_folder):
    datagen = ImageDataGenerator(preprocessing_function=preprocess_input)

    generator = datagen.flow_from_directory(dest_folder,  # this is where you specify the path to the main data folder
                                            target_size=(229, 229),
                                            color_mode='rgb',
                                            batch_size=32,
                                            class_mode='categorical',
                                            shuffle=True)
    return generator


def make_train_generator():
    return _make_generator('./train/')


def make_test_generator():
    return _make_generator('./test/')


train_generator = make_train_generator()
step_size_train = train_generator.n//train_generator.batch_size

# train the model on the new data for a few epochs
model.fit_generator(generator=train_generator,
                    steps_per_epoch=step_size_train,
                    epochs=50,
                    callbacks=[meeshkan_callback,
                               ModelCheckpoint('weights.{epoch:02d}.hdf5')])

# at this point, the top layers are well trained and we can start fine-tuning
# convolutional layers from inception V3. We will freeze the bottom N layers
# and train the remaining top layers.

# let's visualize layer names and layer indices to see how many layers
# we should freeze:
for i, layer in enumerate(base_model.layers):
    print(i, layer.name)

# we chose to train the top 2 inception blocks, i.e. we will freeze
# the first 249 layers and unfreeze the rest:
for layer in model.layers[:249]:
    layer.trainable = False
for layer in model.layers[249:]:
    layer.trainable = True

# we need to recompile the model for these modifications to take effect
# we use SGD with a low learning rate
model.compile(optimizer=SGD(lr=0.0001, momentum=0.9), loss='categorical_crossentropy',
              metrics=[metrics.categorical_accuracy])

# we train our model again (this time fine-tuning the top 2 inception blocks
# alongside the top Dense layers
train_generator = make_train_generator()
step_size_train = train_generator.n // train_generator.batch_size

test_generator = make_test_generator()
step_size_test = test_generator.n // test_generator.batch_size

EPOCHS = 10
TEST_INTERVAL = 1

for i in range(EPOCHS):
    # train the model on the new data for a few epochs
    model.fit_generator(generator=train_generator,
                        steps_per_epoch=step_size_train,
                        epochs=1,
                        callbacks=[meeshkan_callback,
                                   ModelCheckpoint('weights.{epoch:02d}.hdf5')])
    if i % TEST_INTERVAL == 0:
        test_loss, test_accuracy = model.evaluate_generator(generator=test_generator,
                                                            steps=step_size_test)
        meeshkan.report_scalar("Test loss", test_loss, "Test accuracy", test_accuracy)

model.save('tmnt_koopa_%d.h5' % (int(time.time() * 1000),))

test_loss_and_accuracy = model.evaluate_generator(generator=test_generator, steps=step_size_test)
print('test loss and accuracy', test_loss_and_accuracy)
