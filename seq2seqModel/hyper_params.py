import os
import definitions

####
###hyperparameters
####

#dimensions
WORD_EMB_SIZE = 12
LOG_TOKEN_EMB_SIZE = 12
DECODER_HIDDEN_SIZE = 50
LSTM_HIDDEN_SIZE = 30
SENT_EMB_SIZE = 2 * LSTM_HIDDEN_SIZE
HISTORY_LENGTH = 4

#other hyper parameters
LEARNING_RATE = 0.001
BETA = 0.5
EPSILON_FOR_BEAM_SEARCH = 0
MAX_N_EPOCHS = 15

BATCH_SIZE_UNSUPERVISED = 8
BATCH_SIZE_SUPERVISED = 10

USE_BOW_HISTORY = False
    # if true, a binary vector representing the tokens outputted so far in the program is concatenated
    # to the history embedding

IRRELEVANT_TOKENS_IN_GRAD = True
    # if false, a masking is used so that invalid tokens do not affect the gradient.

AUTOMATIC_TOKENS_IN_GRAD = False
    # if false, tokens that are added automatically to a program (when they are the only valid options,
    # are not used when taking the gradient.

HISTORY_EMB_SIZE = HISTORY_LENGTH * LOG_TOKEN_EMB_SIZE

USE_CACHED_PROGRAMS = False
N_CACHED_PROGRAMS = 10 if USE_CACHED_PROGRAMS else 0
LOAD_CACHED_PROGRAMS = False
SAVE_CACHED_PROGRAMS = False

SENTENCE_DRIVEN_CONSTRAINTS_ON_BEAM_SEARCH = True
    # if true, the set of logical tokens that can be used in a parogram is reduced to tokens
    # that can relate to the content of the sentence ()

AVOID_ALL_TRUE_SENTENCES = False
    # if true, the data set of the trainning will incluse only sentences that have also images labeles false.

PRINT_EVERY = 10




#beam settings
MAX_DECODING_LENGTH = 22 # the maximum length of a program from the beam (in number of tokens)
MAX_STEPS = 14 # the default number of decoding steps for a program in the ebam search
BEAM_SIZE = 40
SKIP_AUTO_TOKENS = True
    # if true, tokens that are the only valid option are automatically added to the programs in the bean search,
    # in the same step.

INJECT_TO_BEAM = True and USE_CACHED_PROGRAMS
    # if true, the prefixes of suggested cached programs are injected to the beam at each step, if not in th beam already.




#paths


WORD_EMBEDDINGS_PATH = os.path.join(definitions.SEQ2SEQ_DIR, 'word2vec', 'embeddings_10iters_12dim')
PRE_TRAINED_WEIGHTS = os.path.join(definitions.ROOT_DIR, 'seq2seqModel', 'learnedWeights', 'trained_variables_sup_check_hs4.ckpt')
TRAINED_WEIGHTS_BEST = \
    os.path.join(definitions.ROOT_DIR, 'seq2seqModel' ,'learnedWeightsUns','weights_cached_auto_inj2017-09-09_10_49.ckpt-15')
LOGICAL_TOKENS_LIST =  os.path.join(definitions.DATA_DIR, 'logical forms', 'logical_tokens_list')
CACHED_PROGRAMS = os.path.join(definitions.ROOT_DIR, 'seq2seqModel', 'output decodings', 'cached_programs')
CACHED_PROGRAMS_PRETRAIN = os.path.join(definitions.ROOT_DIR, 'seq2seqModel', 'outputs',
                                        'cached_programs_based_on_pretrain')
NGRAM_PROBS =  os.path.join(definitions.DATA_DIR, 'sentence-processing', 'ngram_logprobs')




