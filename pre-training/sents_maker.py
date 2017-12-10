"""
The methods in this modules were used for generating pairs of english sentences and their logical forms parsings
from pre-annotated patterns of pairs of sentence-logical forms pairs
"""

import pickle
import random
import os
import definitions
from logical_forms import *
from seq2seqModel.partial_program import *
from seq2seqModel.utils import execute
from data_manager import *
from sentence_processing import *



PARSED_FORMS_PATH = os.path.join(definitions.ROOT_DIR, 'pre-training', 'temp_sents_new')
# WORD_EMBEDDINGS_PATH = os.path.join(definitions.ROOT_DIR, 'word2vec', 'embeddings_10iters_12dim')
#
# embeddings_file = open(WORD_EMBEDDINGS_PATH, 'rb')
# embeddings_dict = pickle.load(embeddings_file)
# embeddings_file.close()


colors = ['yellow', 'blue', 'black']
locs = [('top', 'top'), ('bottom', 'bottom')]
ints = ['2', '3', '4', '5', '6', '7']
shapes = ['triangle', 'circle', 'square', ]
quants = [('exactly', 'equal_int'), ('at least', 'ge'), ('at most', 'le')]
ones = ['1']

replacements_dic = {'T_SHAPE' : [('square', ['square']),('triangle', ['triangle']),('circle', ['circle'])],
             'T_COLOR' : [('yellow', ['yellow']),('blue', ['blue']),('black', ['black'])],
             'T_LOC' :  [('top', ['top']),('bottom', ['bottom'])],
             'T_ONE' : [('1', ['1', 'one'])],
             'T_INT' : [(str(i), [str(i)]) for i in range (2,8)],
             'T_QUANTITY_COMPARE' : [('equal_int', ['exactly']),('le', ['at least']),('ge', ['at most']),
                                     ('lt', ['more than']),('gt', ['less than'])]

             }

logical_tokens_mapping = load_functions(LOGICAL_TOKENS_MAPPING_PATH)

WORDS_TO_PATTERNS_PATH = os.path.join(definitions.DATA_DIR, 'sentence-processing', 'formalized words.txt')


def load_forms(path):
    result = {}
    with open(path) as forms_file:
        for line in forms_file:
            if line.startswith('@'):
                engsent = line[2:].rstrip()
                engsent , form_count = engsent.split('$')
                engsent = engsent.strip()
                form_count = int(form_count.strip())
                result[engsent] = (form_count, [])
            elif line.startswith('~'):
                logsent = line[2:].strip()
                result[engsent][1].append(logsent)
            else:
                continue
    return result


def generate_eng_log_pairs(engsent, logsent, n_pairs):
    eng_words = engsent.split()
    forms = set([w for w in eng_words if w == w.upper() and not w.isdigit()])
    result = []
    while len(result) <n_pairs:
        eng_words = engsent.split()
        log_tokens = logsent.split()
        current_replacements = {}
        for f in forms:
            f_ = f[:-2] if f[-1].isdigit() else f
            current_replacements[f] = random.choice(replacements_dic[f_])
        for i, word in enumerate(eng_words):
            if word in current_replacements:
                logtoken, real_words = current_replacements[word]
                eng_words[i] = random.choice(real_words)

        for form, (logtoken, _) in current_replacements.items():
            for i, tok in enumerate(log_tokens):
                if form in tok:
                    newtok = str.upper(logtoken) if '.' in tok else logtoken
                    log_tokens[i] = tok.replace(form, newtok)

        # check sentence is good:
        eng_sent = " ".join(eng_words)
        log_sent = " ".join(log_tokens)
        if 'gt 1' in log_sent or 'ge 1' in log_sent:
            continue
        bad_int_use = False
        for j in (3,4,5,6,7):
            if np.random.rand() < 0.10 * j:
                continue
            if '{} tower'.format(j) in eng_sent or '{} box'.format(j) in eng_sent\
                    or '{} ALL_BOXES'.format(j) in log_sent:
                bad_int_use =True
                break


        if not bad_int_use:
            result.append((eng_sent, log_sent))
    return result


def test_generated_forms(forms_dictionary, samples):
    next_token_probs_getter = lambda pp: (pp.get_possible_continuations(), [0.1 for p in pp.get_possible_continuations()])


    i = 0
    for engsent, (form_count, logsents) in sorted(forms_dictionary.items(), key = lambda k : - k[1][0]):
        for logsent in logsents:
            curr_samples = random.sample(samples, 1)
            generated_forms = generate_eng_log_pairs(engsent, logsent, 5)
            for gen_sent, gen_log in generated_forms:
                i+=1
                print(i)
                for word in gen_sent.split():
                    if word not in embeddings_dict:
                        raise ValueError('word {} is not in vocabulary'.format(word))

                for sample in curr_samples:
                    r = execute(gen_log.split(), sample.structured_rep, logical_tokens_mapping)
                    if r is None:
                        print("not compiled:")
                        print(gen_log)
                        print("original=" + logsent)
                        print()
                if not "filter filter filter" in gen_log:
                    try:
                        prog = program_from_token_sequence(next_token_probs_getter, gen_log.split(), logical_tokens_mapping)
                    except ValueError:

                        print(gen_sent)
                        print(gen_log)


def generate_pairs_for_supervised_learning(forms_dictionary):
    forms_dictionary = {a: (b, [c[0]]) for a, (b, c) in forms_dictionary.items()}
    all_pairs =[]
    parsing_dict = {}
    for engsent, (form_count, logsents) in sorted(forms_dictionary.items(), key=lambda k: - k[1][0]):
        for logsent in logsents:
            num = int(50 *form_count**(0.8)) // len(logsents)
            all_pairs.extend(generate_eng_log_pairs(engsent, logsent, num))

    for k,v in all_pairs:
        parsing_dict[k] = v

    pairs = [(k,v) for k,v in parsing_dict.items()]

    n = len(pairs)
    np.random.shuffle(pairs)
    pairs_train = pairs[: int( 0.9 * n)]
    pairs_validation = pairs[int( 0.9 * n): ]

    return pairs_train, pairs_validation


def extract_all_sentences_in_given_patterns(sentences, patterns):
    formalized = get_sentences_formalized(sentences)
    result = {}
    for k, s in formalized.items():
        if s in patterns:
            result[k] = sentences[k]
    return result


def get_sentences_formalized(sentences):
    dict = load_dict_from_txt(WORDS_TO_PATTERNS_PATH)
    for i in range(2,10):
        dict[str(i)] = 'T_INT'
    dict["1"] = 'T_ONE'
    dict["one"] = 'T_ONE'
    dict["a single"] = 'T_ONE'
    formalized_sentences =  replace_words_by_dictionary(sentences, dict)
    return formalized_sentences

def replaced(s, dict):
    s = ' '+s+' '
    for item in dict:
        newitem = ' '+item+' '
        value = ' '+dict[item]+' '
        s = s.replace(newitem, value)
    s = s.strip()
    return s

def get_new_patterns():
    train = definitions.TRAIN_JSON
    data = read_data(train)
    samples, sents_dict = build_data(data, preprocessing_type='deep')
    formalized_sentences = get_sentences_formalized(sents_dict)
    patterns_counter = {}
    for key in formalized_sentences:
        sent = formalized_sentences[key]
        if sent not in patterns_counter:
            patterns_counter[sent] = 1
        else:
            patterns_counter[sent] += 1
    return patterns_counter

def create_new_patterns_dict():
    patterns_counter = get_new_patterns()
    old_patterns_dict = load_forms(definitions.DATA_DIR + r'\parsed sentences\formalized_parsed_sentences_for_supervised_training.txt')
    replacements_dict = load_dict_from_txt(OLD_SYNONYMS_PATH)
    new_patterns_dict = {}
    for pattern in patterns_counter:
        replaced_pattern = replaced(pattern, replacements_dict)
        if replaced_pattern in old_patterns_dict:
            new_patterns_dict[pattern] = (patterns_counter[pattern], old_patterns_dict[replaced_pattern][1])
    for pattern in old_patterns_dict:
        if pattern not in new_patterns_dict:
            new_patterns_dict[pattern] = old_patterns_dict[pattern]
    return new_patterns_dict

def pairs_for_abstract_supervised_learning(new_dict):
    '''
    :param new_dict: {abs_sent(str): (freq(int), [abs_prog(str)])}
    :return: [(abs_sent(str), abs_prog(str))]
    '''

    pairs = []
    for abs_sent in new_dict:
        pairs.append((abs_sent, new_dict[abs_sent][1][0]))
        # for abs_prog in new_dict[abs_sent][1]:
        #     pairs.append((abs_sent, abs_prog))

    n = len(pairs)
    np.random.shuffle(pairs)
    pairs_train = pairs[: int( 0.9 * n)]
    pairs_validation = pairs[int( 0.9 * n) :]

    return pairs_train, pairs_validation

if __name__ == '__main__':

    # new_dict = create_new_patterns_dict()
    # pairs_train, pairs_validation = generate_pairs_for_supervised_learning(new_dict)
    #
    # datas = (definitions.TRAIN_JSON,definitions.DEV_JSON,definitions.TEST_JSON)
    # for d in datas:
    #     data = read_data(d)
    #     samples, _ = build_data(data, preprocessing_type='deep')
    #     include = 0
    #     quads = {}
    #     for sample in samples:
    #         idx = sample.identifier.split('-')[0]
    #         if (idx, sample.sentence) not in quads:
    #             quads[(idx, sample.sentence)] = [sample]
    #         else:
    #             quads[(idx, sample.sentence)].append(sample)
    #     for quad in quads:
    #         sent = quad[1]
    #         labels = [s.label for s in quads[quad]]
    #         tempdict = {'1': sent}
    #         formalized_sent = get_sentences_formalized(tempdict)['1']
    #         if formalized_sent in new_dict:
    #             include += 1
    #         elif all(labels) == True:
    #             include +=1
    #     print(len(quads), include)
    #     print(include/len(quads))

    np.random.seed(0)
    new_dict = create_new_patterns_dict()
    if ABSTRACTION:
        pairs_train, pairs_validation = pairs_for_abstract_supervised_learning(new_dict)
    else:
        pairs_train, pairs_validation = generate_pairs_for_supervised_learning(new_dict)

    print(len(pairs_train), len(pairs_validation))
    pickle.dump(pairs_train, open(definitions.SUPERVISED_TRAIN_PICKLE, 'wb'))
    pickle.dump(pairs_validation, open(definitions.SUPERVISED_VALIDATION_PICKLE, 'wb'))

    # newpath = definitions.DATA_DIR + r'\parsed sentences\new_formalized_parsed_sentences_for_supervised_training.txt'
    # with open(newpath, 'w') as f:
    #     for item in new_dict:
    #         tup = new_dict[item]
    #         f.write('\n@ ' + item + ' $ ' + str(tup[0]) + '\n')
    #         for prog in tup[1]:
    #             f.write('~ ' + prog + '\n')





