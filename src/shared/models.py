import os

from keras.layers import Dense, Conv1D, BatchNormalization, GlobalMaxPooling1D, Dropout, MaxPooling1D
from keras.models import Sequential, load_model, save_model
from keras.regularizers import l2
from sklearn import pipeline

from shared import transformers
from shared.common import get_hash_of_dict
from shared.batch_classifier import KerasBatchClassifier


DEFAULT_MODEL_DIRECTORY = '../dist/models'


class Model(object):

    NAME = 'undefined'

    def __init__(self, dataset_id, **model_params):
        self.dataset_id = dataset_id
        self.model_params = model_params
        self._pipeline = None

    def __getattr__(self, item):
        if self._pipeline is None:
            raise RuntimeError("You must load model first!")
        return getattr(self._pipeline, item)

    @property
    def loaded(self):
        return self._pipeline is not None

    @property
    def model(self):
        raise NotImplementedError()

    @property
    def filename(self):
        h = get_hash_of_dict(self.model_params)
        return '{}_{}_{}.h5'.format(self.NAME, self.dataset_id, h.hexdigest()[:8])

    def load(self, directory=DEFAULT_MODEL_DIRECTORY):
        raise NotImplementedError()

    def save(self, directory=DEFAULT_MODEL_DIRECTORY):
        raise NotImplementedError()

    def train(self, X, y):
        raise NotImplementedError()

    def summary(self):
        raise NotImplementedError()


class KerasModel(Model):

    NAME = 'keras'

    def __init__(self, nlp, dataset_id, **model_params):
        model_params.setdefault('epochs', 20)
        model_params.setdefault('batch_size', 128)
        model_params.setdefault('max_words_in_sentence', 200)
        self.nlp = nlp
        self.max_words_in_sentence = model_params['max_words_in_sentence']
        super().__init__(dataset_id, **model_params)

    @property
    def model(self):
        if self._pipeline is None:
            raise RuntimeError("You must load model first!")
        model_step = self._pipeline.steps[-1][1]
        return model_step.model

    def load(self, directory=DEFAULT_MODEL_DIRECTORY):
        filepath = os.path.join(directory, self.filename)
        model = load_model(filepath=filepath)
        self._pipeline = self.get_pipeline(model)
        return self

    def train(self, X, y, train_indices=None, test_indices=None):
        pipe = self.get_pipeline()
        pipe.fit(X, y, keras__train_indices=train_indices, keras__test_indices=test_indices)
        self._pipeline = pipe
        model_step = pipe.steps[-1][1]
        return model_step.history

    def save(self, directory=DEFAULT_MODEL_DIRECTORY):
        filepath = os.path.join(directory, self.filename)
        save_model(self.model, filepath)

    def get_pipeline(self, model=None):
        main_pipeline = [
            ('clear', transformers.ClearTextTransformer()),
            ('nlp_index', transformers.WordsToNlpIndexTransformer(self.nlp))
        ]
        batch_pipeline = [
            ('nlp_input', transformers.NlpIndexToInputVectorTransformer(self.nlp, self.max_words_in_sentence))
        ]

        classifier = KerasBatchClassifier(
            build_fn=self._build_conv1d,
            preprocess_pipeline=pipeline.Pipeline(batch_pipeline),
            **self.model_params)

        if model:
            classifier.model = model

        return pipeline.Pipeline(main_pipeline + [('keras', classifier)])

    def summary(self):
        return self.model.summary()

    @staticmethod
    def _build_conv1d(max_words_in_sentence=200, embedding_dim=300, filters=32, kernel_size=5, l2_weight=0.001,
                     dropout_rate=0.7):
        model = Sequential([
            Conv1D(
                filters, kernel_size, strides=1, kernel_regularizer=l2(l2_weight),
                input_shape=(max_words_in_sentence, embedding_dim), padding='valid', activation='relu'),
            MaxPooling1D(5),
            BatchNormalization(),
            Conv1D(
                2 * filters, kernel_size, strides=1, kernel_regularizer=l2(l2_weight),
                input_shape=(max_words_in_sentence, embedding_dim), padding='valid', activation='relu'),
            GlobalMaxPooling1D(),
            BatchNormalization(),
            Dropout(dropout_rate),
            Dense(1, kernel_regularizer=l2(l2_weight), activation='sigmoid'),
        ])
        model.compile(loss='mean_squared_error', optimizer='adam', metrics=['accuracy'])
        return model
