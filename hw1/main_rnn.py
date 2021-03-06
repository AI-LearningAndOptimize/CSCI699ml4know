"""
Train RNN models
"""

import pprint

import numpy as np
import torch.optim as optim
from sklearn.model_selection import train_test_split

from classifier.model import RNNModel, cross_entropy_with_mask
from classifier.rnn import RNNClassifier
from utils import enable_cuda
from utils.data_converter import read_data, extract_columns, append_column, data_to_output
from utils.feature.word_embedding import load_glove6B, build_embedding_matrix, RNNFeatureExtractor
from utils.vocab import build_vocab

loss_fn_dict = {
    'cross_entropy': cross_entropy_with_mask,
    'macro_f1': None
}


def get_checkpoint_path(architecture, n_layers, manual, loss_fn, embed_dim):
    return 'checkpoint/rnn_{}_{}_{}_{}_{}.ckpt'.format(architecture, n_layers, manual, loss_fn, embed_dim)


def make_parser():
    import argparse
    parser = argparse.ArgumentParser(description='Arguments for training RNN-based model')
    parser.add_argument('-a', '--architecture', type=str, choices=['lstm', 'bilstm', 'cnn'])
    parser.add_argument('-nl', '--n_layers', type=int, default=1)
    parser.add_argument('-mf', '--manual_feature', action='store_true')
    parser.add_argument('-l', '--loss_fn', type=str, choices=loss_fn_dict.keys(), default='cross_entropy')
    parser.add_argument('-d', '--embed_dim', type=int, choices=[50, 100, 200, 300], default=50)

    subparsers = parser.add_subparsers()
    train_parser = subparsers.add_parser('train')
    train_parser.add_argument('-lr', '--learning_rate', type=float, default=1e-3)
    train_parser.add_argument('-ne', '--num_epoch', type=int, default=20)
    train_parser.set_defaults(func=train)

    eval_parser = subparsers.add_parser('eval', help='If the test file contains label, print performance report, '
                                                     'else output a file with labels')
    eval_parser.add_argument('-f', '--infile')
    eval_parser.set_defaults(func=eval)

    predict_parser = subparsers.add_parser('predict', help='If the test file contains label, print performance report, '
                                                           'else output a file with labels')
    predict_parser.add_argument('-f', '--infile')
    predict_parser.add_argument('-o', '--outfile')
    predict_parser.set_defaults(func=predict)

    return parser


def build_classifier(architecture, n_layers, manual, loss_fn, embedding_matrix, learning_rate, embed_dim, max_len=None):
    _, word_index, index_to_label, labels_index, _, pos_index = build_vocab()
    if embedding_matrix is None:
        embedding_matrix = np.random.randn(len(word_index), embed_dim)
    feature_extractor = RNNFeatureExtractor(word_index, labels_index, pos_index, include_manual_features=manual,
                                            max_len=max_len)
    additional_feature_dim = feature_extractor.get_additional_feature_dim()
    rnn_model = RNNModel(architecture, embedding_matrix, additional_feature_dim, len(index_to_label), n_layers=n_layers)
    if enable_cuda:
        rnn_model.cuda()

    if learning_rate:
        optimizer = optim.Adam(rnn_model.parameters(), lr=learning_rate)
    else:
        optimizer = None

    classifier = RNNClassifier(feature_extractor, index_to_label, rnn_model, optimizer, loss_fn_dict[loss_fn],
                               enable_cuda=enable_cuda)

    return classifier


def train(args):
    args = vars(args)
    pprint.pprint(args)
    architecture = args['architecture']
    n_layers = args['n_layers']
    manual_feature = args['manual_feature']
    loss_fn = args['loss_fn']
    embed_dim = args['embed_dim']
    learning_rate = args['learning_rate']
    num_epoch = args['num_epoch']

    checkpoint_path = get_checkpoint_path(architecture, n_layers, manual_feature, args['loss_fn'], embed_dim)

    sentences = read_data('data/onto.train')
    vocab, word_index, index_to_label, labels_index, all_pos, pos_index = build_vocab()
    total_num_sentences = len(sentences)
    print('Total number of sentences: {}'.format(total_num_sentences))
    train_sentences, val_sentences = train_test_split(sentences, test_size=0.25, random_state=123, shuffle=True)
    glove_model = load_glove6B(dimension=embed_dim)
    embedding_matrix = build_embedding_matrix(glove_model, vocab)
    del glove_model, vocab, all_pos

    classifier = build_classifier(architecture, n_layers, manual_feature, loss_fn, embedding_matrix, learning_rate,
                                  embed_dim)

    classifier.fit(train_sentences, val_sentences, num_epoch=num_epoch, verbose=True,
                   checkpoint_path=checkpoint_path)

    classifier.load_checkpoint(checkpoint_path)

    test_a_sentences = read_data('data/onto.testa')
    precision, recall, f1_score = classifier.evaluate(test_a_sentences)
    print('Result on onto.testa: Precition {}, Recall {}, F1 {}'.format(precision, recall, f1_score))

def predict(args):
    args = vars(args)
    pprint.pprint(args)
    architecture = args['architecture']
    n_layers = args['n_layers']
    manual_feature = args['manual_feature']
    embed_dim = args['embed_dim']
    infile = args['infile']
    outfile = args['outfile']
    loss_fn = args['loss_fn']

    checkpoint_path = get_checkpoint_path(architecture, n_layers, manual_feature, loss_fn, embed_dim)
    classifier = build_classifier(architecture, n_layers, manual_feature, loss_fn, None, None, embed_dim,
                                  max_len=300)
    classifier.load_checkpoint(checkpoint_path)

    test_sentence = read_data(infile)
    result = classifier.predict(test_sentence)

    test_sentence_label = extract_columns(append_column(test_sentence, result), indexs=[-1])
    data_to_output(test_sentence_label, write_to_file=outfile)


def eval(args):
    args = vars(args)
    pprint.pprint(args)
    architecture = args['architecture']
    n_layers = args['n_layers']
    manual_feature = args['manual_feature']
    embed_dim = args['embed_dim']
    infile = args['infile']
    loss_fn = args['loss_fn']

    checkpoint_path = get_checkpoint_path(architecture, n_layers, manual_feature, loss_fn, embed_dim)
    classifier = build_classifier(architecture, n_layers, manual_feature, loss_fn, None, None, embed_dim,
                                  max_len=300)
    classifier.load_checkpoint(checkpoint_path)
    test_data = read_data(infile)
    precision, recall, f1_score = classifier.evaluate(test_data)
    print('Result: Precition {}, Recall {}, F1 {}'.format(precision, recall, f1_score))


if __name__ == '__main__':
    parser = make_parser()
    args = parser.parse_args()
    args.func(args)
