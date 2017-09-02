import tensorflow as tf
from tensorflow.contrib.rnn import BasicLSTMCell
from seq2seqModel.utils import *
from seq2seqModel.logical_forms_generator import *
from handle_data import CNLVRDataSet, SupervisedParsing
import pickle
import numpy as np
import time
import os
import definitions

#paths

LOGICAL_TOKENS_MAPPING_PATH = os.path.join(definitions.DATA_DIR, 'logical forms', 'token mapping_limitations')
LOGICAL_TOKENS_EMBEDDINGS_PATH = os.path.join(definitions.DATA_DIR, 'logical forms', 'logical_tokens_embeddings')
WORD_EMBEDDINGS_PATH = os.path.join(definitions.ROOT_DIR, 'word2vec', 'embeddings_10iters_12dim')
PARSED_EXAMPLES_T = os.path.join(definitions.DATA_DIR, 'parsed sentences', 'parses for check as tokens')

####
###hyperparameters
####

#dimensions
words_embedding_size = 12
logical_tokens_embedding_size = 12
decoder_hidden_layer_size = 50
lstm_hidden_layer_size = 30
sent_embedding_size = 2 * lstm_hidden_layer_size
history_length = 4
history_embedding_size = history_length * logical_tokens_embedding_size

#other hyper parameters
learning_rate = 0.0005
beta = 0.5
epsilon_for_e_greedy = 0.5
num_of_steps = 10000
max_decoding_length = 20
beam_size = 50
batch_size = 8
batch_size_supervised = 10




# load word embeddings
embeddings_file = open(WORD_EMBEDDINGS_PATH,'rb')
embeddings_dict = pickle.load(embeddings_file)
embeddings_file.close()
assert words_embedding_size == np.size(embeddings_dict['blue'])



#load logical tokens inventory
logical_tokens_mapping = load_functions(LOGICAL_TOKENS_MAPPING_PATH)
#logical_tokens = [token for token in logical_tokens_mapping.keys()] ####TODO change here to load from file
#pickle.dump(logical_tokens,open('logical_tokens_list','wb'))
logical_tokens = pickle.load(open('logical_tokens_list','rb'))
for var in "xyzwuv":
    logical_tokens.extend([var, 'lambda_{}_:'.format(var) ])
logical_tokens.extend(['<s>', '<EOS>'])
logical_tokens_ids = {lt: i for i, lt in enumerate(logical_tokens)}
n_logical_tokens = len(logical_tokens_ids)



ngram_p_dict = get_probs_from_file(PARSED_EXAMPLES_T)


def build_sentence_encoder():

    # placeholders for sentence and it's length
    sentence_placeholder = tf.placeholder(shape = [None, None,words_embedding_size],dtype = tf.float32,name = "sentence_placeholder")
    sent_lengths = tf.placeholder(dtype = tf.int32,name = "sent_length_placeholder")

    # Forward cell
    lstm_fw_cell = BasicLSTMCell (lstm_hidden_layer_size, forget_bias=1.0)
    # Backward cell
    lstm_bw_cell = BasicLSTMCell(lstm_hidden_layer_size, forget_bias=1.0)
    # stack cells together in RNN
    outputs, _ = tf.nn.bidirectional_dynamic_rnn(lstm_fw_cell, lstm_bw_cell, sentence_placeholder,sent_lengths,dtype=tf.float32)
    #    outputs: A tuple (output_fw, output_bw) containing the forward and the backward rnn output `Tensor`.
    #    both output_fw, output_bw will be a `Tensor` shaped: [batch_size, max_time, cell_fw.output_size]`

    # outputs is a (output_forward,output_backwards) tuple. concat them together to receive h vector
    lstm_outputs = tf.concat(outputs,2)[0]    # shape: [batch_size, max_time, 2 * hidden_layer_size ]
    # the final utterance is the last output

    final_fw = outputs[0][:,-1,:]
    final_bw = outputs[1][:,0,:]

    return sentence_placeholder, sent_lengths, lstm_outputs, tf.concat((final_fw, final_bw), axis=1)


def build_decoder(lstm_outputs, final_utterance_embedding):
    history_embedding = tf.placeholder(shape=[None, history_embedding_size], dtype=tf.float32, name="history_embedding")
    num_rows = tf.shape(history_embedding)[0]
    e_m_tiled = tf.tile(final_utterance_embedding, ([num_rows, 1]))
    decoder_input = tf.concat([e_m_tiled, history_embedding], axis=1)
    W_q = tf.get_variable("W_q", shape=[decoder_hidden_layer_size, sent_embedding_size + history_embedding_size],
                          initializer=tf.contrib.layers.xavier_initializer())  # (d1,100)
    q_t = tf.nn.relu(tf.matmul(W_q, tf.transpose(decoder_input)))  # dim [d1,1]
    W_a = tf.get_variable("W_a", shape=[decoder_hidden_layer_size, sent_embedding_size],
                          initializer=tf.contrib.layers.xavier_initializer())  # dim [d1*60]
    alpha = tf.nn.softmax(tf.matmul(tf.matmul(tf.transpose(q_t), W_a), tf.transpose(lstm_outputs)))  # dim [1,25]
    c_t = tf.matmul(alpha, lstm_outputs)  # attention vector, dim [1,60]
    W_s = tf.get_variable("W_s", shape=[logical_tokens_embedding_size, decoder_hidden_layer_size + sent_embedding_size],
                          initializer=tf.contrib.layers.xavier_initializer())
    W_logical_tokens = tf.get_variable("W_logical_tokens", dtype= tf.float32,
                    shape=[n_logical_tokens, logical_tokens_embedding_size],
                          initializer=tf.contrib.layers.xavier_initializer())
    token_unnormalized_dist = tf.matmul(W_logical_tokens, tf.matmul(W_s, tf.concat([q_t, tf.transpose(c_t)], 0)))

    return history_embedding, token_unnormalized_dist, W_logical_tokens


def build_batchGrad():
    lstm_fw_weights_grad = tf.placeholder(tf.float32, name="lstm_fw_weights_grad")
    lstm_fw_bias_grad = tf.placeholder(tf.float32, name="lstm_fw_bias_grad")
    lstm_bw_weights_grad = tf.placeholder(tf.float32, name="lstm_bw_weights_grad")
    lstm_bw_bias_grad = tf.placeholder(tf.float32, name="lstm_bw_bias_grad")
    wq_grad = tf.placeholder(tf.float32, name="wq_grad")
    wa_grad = tf.placeholder(tf.float32, name="wa_grad")
    ws_grad = tf.placeholder(tf.float32, name="ws_grad")
    logical_tokens_grad = tf.placeholder(tf.float32, name="logical_tokens_grad")
    batchGrad = [lstm_fw_weights_grad, lstm_fw_bias_grad, lstm_bw_weights_grad, lstm_bw_bias_grad,
                 wq_grad, wa_grad, ws_grad, logical_tokens_grad]
    return batchGrad

# PartialProgram


def sample_valid_decodings(next_token_probs_getter, n_decodings):
    decodings = []
    while len(decodings)<n_decodings:
        partial_program = PartialProgram()
        for t in range(max_decoding_length+1):
            if t > 0 and partial_program[-1] == '<EOS>':
                decodings.append(partial_program)
                break
            valid_next_tokens, probs_given_valid = \
                next_token_probs_getter(partial_program)
            if not valid_next_tokens:
                break
            next_token = np.random.choice(valid_next_tokens, p= probs_given_valid)
            p = probs_given_valid[valid_next_tokens.index(next_token)]
            partial_program.add_token(next_token, np.log(p), logical_tokens_mapping)
    return decodings


def sample_decoding_prefixes(next_token_probs_getter, n_decodings, length):
    decodings = []
    while len(decodings)<n_decodings:
        partial_program = PartialProgram()
        for t in range(length):
            if t > 0 and partial_program[-1] == '<EOS>':
                decodings.append(partial_program)
                break
            valid_next_tokens, probs_given_valid = \
                next_token_probs_getter(partial_program)
            if not valid_next_tokens:
                break
            next_token = np.random.choice(valid_next_tokens, p= probs_given_valid)
            p = probs_given_valid[valid_next_tokens.index(next_token)]
            partial_program.add_token(next_token, np.log(p), logical_tokens_mapping)
        decodings.append(partial_program)
    return decodings

def create_partial_program(next_token_probs_getter, token_seq):
    partial_program = PartialProgram()
    for tok in token_seq:
        valid_next_tokens, probs_given_valid = \
            next_token_probs_getter(partial_program)
        if tok not in valid_next_tokens:
            return None
        p = probs_given_valid[valid_next_tokens.index(tok)]
        partial_program.add_token(tok, np.log(p), logical_tokens_mapping)
    return partial_program


def beam_search(next_token_probs_getter, epsilon = epsilon_for_e_greedy):


    beam = [PartialProgram()]
    # create a beam of possible programs for sentence, the iteration continues while there are unfinished programs in beam and t < max_beam_steps

    for t in range(max_decoding_length):
        # if t>1 :
        #     sampled_prefixes = sample_decoding_prefixes(next_token_probs_getter, 5, t)
        #     beam.extend(sampled_prefixes)
        continuations = {}

        for partial_program in beam:
            if t > 0 and partial_program[-1] == '<EOS>':
                continuations[partial_program] = [partial_program]
                continue

            cont_list = []

            valid_next_tokens, probs_given_valid = \
                next_token_probs_getter(partial_program)

            logprob_given_valid = np.log(probs_given_valid)

            #ngram_probs = get_ngram_probs(history_tokens, ngram_p_dict, valid_next_tokens)

            for i, next_tok in enumerate(valid_next_tokens):
                pp = PartialProgram(partial_program)
                pp.add_token(next_tok, logprob_given_valid[i] , logical_tokens_mapping)
                cont_list.append(pp)
            continuations[partial_program] = cont_list

        # choose the #beam_size programs and place them in the beam
        all_continuations_list = [c for p in continuations.values() for c in p]
        all_continuations_list.sort(key=lambda c: - c.logprob)
        beam = epsilon_greedy_sample(all_continuations_list, beam_size, continuations, epsilon)

        if all([prog.token_seq[-1] == '<EOS>' for prog in beam]):
            break  # if we have beam_size full programs, no need to keep searching
    return beam


def get_next_token_probs(partial_program, logical_tokens_embeddings_dict, decoder_feed_dict, history_embedding_tensor,
                         token_prob_dist, sentence_logical_tokens_mapping = logical_tokens_mapping):
    history_tokens = ['<s>' for _ in range(history_length - len(partial_program))] + \
                     partial_program[-history_length:]
    history_embs = [logical_tokens_embeddings_dict[tok] for tok in history_tokens]
    history_embs = np.reshape(np.concatenate(history_embs), [1, history_embedding_size])
    # run forward pass
    decoder_feed_dict[history_embedding_tensor] = history_embs
    current_probs = np.squeeze(sess.run(token_prob_dist, feed_dict=decoder_feed_dict))

    valid_next_tokens = partial_program.get_possible_continuations(sentence_logical_tokens_mapping)

    probs_given_valid = [1.0] if len(valid_next_tokens) == 1 else \
        [current_probs[logical_tokens_ids[next_tok]] for next_tok in valid_next_tokens]
    # TODO document
    probs_given_valid = probs_given_valid / np.sum(probs_given_valid)
    ngram_probs_given_valid = get_ngram_probs(history_tokens, ngram_p_dict, valid_next_tokens)
    probs = (probs_given_valid + 4 * ngram_probs_given_valid)/5
    probs /= probs.sum()
    return valid_next_tokens, probs

def get_gradient_weights_for_beam(beam_rewarded_programs):

    beam_log_probs = np.array([prog.logprob for prog in beam_rewarded_programs])
    q_mml = softmax(beam_log_probs)
    return np.power(q_mml,beta) / np.sum(np.power(q_mml,beta))


def sentences_to_embeddings(sentences, enbedding_dict): #TODO is it supposed to be "embeddings_dict"?
    return np.array([[embeddings_dict.get(w, embeddings_dict['<UNK>']) for w in sentence] for sentence in sentences])



def run_unsupervised_inference(sess):

    # build the computaional graph:
    # bi-lstm encoder - given a sentence (of a variable length) as a sequence of word embeddings,
    # and returns the lstm outputs.
    sentence_placeholder, sent_lengths_placeholder, h, e_m = build_sentence_encoder()
    # ff decoder - given the outputs of the encoder, and an embedding of the decoding history,
    # computes a probability distribution over the tokens.
    history_embedding_placeholder, token_unnormalized_dist, W_logical_tokens = build_decoder(h, e_m)
    token_prob_dist_tensor = tf.nn.softmax(token_unnormalized_dist,dim=0)
    chosen_logical_tokens = tf.placeholder(tf.float32, [None, n_logical_tokens],  ##
                                   name="chosen_action_token")  # a one-hot vector represents the action taken at each step

    # the log-probability according to the model of a program given an input sentnce.
    program_log_prob = tf.reduce_sum(tf.log(token_prob_dist_tensor) * tf.transpose(chosen_logical_tokens))
    theta = tf.trainable_variables()
    optimizer = tf.train.AdamOptimizer(learning_rate=learning_rate)
    compute_program_grads = optimizer.compute_gradients(program_log_prob)
    batch_grad = build_batchGrad()
    update_grads = optimizer.apply_gradients(zip(batch_grad, theta))

    #init = tf.global_variables_initializer()
    saver = tf.train.Saver()
    saver.restore(sess, os.path.join(os.getcwd(), 'trained_variables2.ckpt'))
    #saver.restore(sess, os.path.join(os.getcwd(), 'trained_variables_unsupervised.ckpt'))


    # load data
    train = CNLVRDataSet(definitions.TRAIN_JSON)

    current_logical_tokens_embeddings = sess.run(W_logical_tokens)
    logical_tokens_embeddings_dict = \
        {token: current_logical_tokens_embeddings[logical_tokens_ids[token]] for token in logical_tokens}

    empty_beam = 0
    batch_size = 1
    correct_avg = 0
    correct_first = 0
    total = 0

    for sample in train:
        print("train.epochs_completed= {}".format(train.epochs_completed))
        print("previous empty beams num: %d" % empty_beam)
        empty_beam = 0

        sentences = sample.sentence
        label = sample.label

        embedded_sentences = sentences_to_embeddings(sentences, embeddings_dict)

        for step in range(batch_size):

            s = (sentences[step]).split()
            x = embedded_sentences[step]

            sentence_embedding = np.reshape(x, [1, len(x), words_embedding_size])
            length = [len(s)]
            sentence_h, sentence_e_m = sess.run([h, e_m], feed_dict=
                                    {sentence_placeholder: sentence_embedding, sent_lengths_placeholder: length})
            decoder_feed_dict = {e_m: sentence_e_m, h: sentence_h}
            sentence_logical_tokens_mapping = {k:v for k,v in logical_tokens_mapping.items() if
                                               not v.necessity or any(w in s for w in v.necessity)}

            next_token_probs_getter = lambda pp :  get_next_token_probs(pp, logical_tokens_embeddings_dict, decoder_feed_dict,
                                                                        history_embedding_placeholder,
                                                                        token_prob_dist_tensor, sentence_logical_tokens_mapping)

            beam = beam_search(next_token_probs_getter)
            beam = [prog for prog in beam if prog.token_seq[-1] == '<EOS>'] #otherwise won't compile and therefore no reward

            if len(beam) == 0:
                empty_beam += 1
            execution_results = []
            for prog in beam:
                prog.token_seq.pop(-1) # take out the '<EOS>' token
                execution_results.append(execute(prog.token_seq,sample.structured_rep,logical_tokens_mapping))

            correct_avg += 1 if np.array(execution_results).mean() == label else 0
            correct_first += 1 if execution_results[0] == label else 0
            total += 1



    print("accuracy for average of beam: %.2f" % (correct_avg / total))
    print("accuracy for largest p in beam: %.2f" % (correct_first / total))







if __name__ == '__main__':
    with tf.Session() as sess:
        run_unsupervised_inference(sess)