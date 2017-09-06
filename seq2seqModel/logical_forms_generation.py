'''
decoder poc
'''

from collections import namedtuple
import numpy as np
import os
import re


from preprocessing import get_ngrams_counts
import definitions
from logical_forms_new import process_token_sequence
from preprocessing import *
from general_utils import *

TOKEN_MAPPING = os.path.join(definitions.DATA_DIR, 'logical forms', 'token mapping_limitations')
PARSED_EXAMPLES_T = os.path.join(definitions.DATA_DIR, 'parsed sentences', 'parses for check as tokens')
LOGICAL_TOKENS_EMBEDDINGS_PATH = os.path.join(definitions.DATA_DIR, 'logical forms', 'logical_tokens_embeddings')
MAX_LENGTH = 25

USE_PARAPHRASING = False

TokenTypes = namedtuple('TokenTypes', ['return_type', 'args_types', 'necessity'])

log_dict = {'yellow': 'yellow', 'blue': 'blue', 'black': 'black', 'top': 'top', 'bottom': 'bottom',
            'exactly': 'equal_int', 'at least': 'ge', 'at most': 'le', 'triangle': 'triangle',
            'circle': 'circle', 'square': 'square', '2': '2', '3': '3', '4': '4', '5': '5', '6': '6',
            '7': '7', '1': '1', 'one': '1'}


def get_probs_from_file(path):
    token_seqs = []
    with open(path) as parsed_examples:
        for line in parsed_examples:
            if line.isspace():
                continue
            line = line.strip()
            if line.startswith('#'):
                continue
            if not line[0].isdigit():
                token_seqs.append(line.split())

    return get_ngrams_counts(token_seqs, 3, include_start_and_stop=True)


def load_functions(filename):
    """
    loads from file a dictionary of all valid tokens in the formal language we use.
    each token is is defines by its name, its return types, and its argument types.
    tokens that represent known entities, like ALL_BOXES, or Color.BLUE are treated as
    functions that take no arguments, and their return type is their own type, i.e. 
    set<set<Item>>, and Color, correspondingly.
    """
    functions_dict = {}
    with open(filename) as functions_file:
        for i, line in enumerate(functions_file):
            if line.isspace():
                continue
            line = line.strip()
            if line.startswith('#'):
                continue
            entry = line.split()

            split_idx = entry.index(':') if ':' in entry else len(entry)
            entry, necessary_words = entry[:split_idx], entry[split_idx:]

            if len(entry) < 3 or not entry[1].isdigit() or int(entry[1]) != len(entry) - 3:
                print("could not parse function in line  {0}: {1}".format(i, line))
                # should use Warning instead
                continue
            token, return_type, args_types = entry[0], entry[-1], entry[2:-1]
            functions_dict[token] = TokenTypes(return_type=return_type, args_types=args_types, necessity= necessary_words)
        functions_dict['1'] = TokenTypes(return_type='int', args_types=[], necessity=['1', 'one', 'a', 'is'])
        functions_dict.update({str(i): TokenTypes(return_type='int', args_types=[], necessity=[str(i)]) for i in range(2, 10)})

    return functions_dict


def check_types(required, suggested):
    '''
    utility function to check whether the return type of a candidate token
    matches the type in the top of the stack.
    :param required: a str or a list of strings representing types in the logical forms.
    :param suggested: a string representing a type in the logical forms
    :return: True if the provided return type matches the required type that is in the top of the stack. 

    '''
    if '|' in required:  # if there are several possible required types (e.g. Item and set<Item>)
        return any([check_types(x, suggested) for x in required.split('|')])

    if required == suggested:
        return True
    if required == '?' or suggested == '?':  # wildcard
        return True
    if required.startswith('set') and suggested.startswith('set'):
        return check_types(required[4:-1], suggested[4:-1])
    if required.startswith('bool_func') and suggested.startswith('bool_func'):
        return check_types(required[10:-1], suggested[10:-1])

    return False


def disambiguate(typed, nontyped):
    '''
    utility function that "reveals" the runtime type of a wildcard '?' for to typed that where checked.
    e.g. for set<Item> and set<?> return 'Item'.
    :param typed: a str or a list of strings representing types in the logical forms.
    :param nontyped: a string representing a type in the logical forms
    :return: the type that replaces '?', or None if there is no such matching. 
    '''
    if not isinstance(typed, str):
        raise ValueError('{} is not a string'.format(typed))
    if not isinstance(nontyped, str):
        raise ValueError('{} is not a string'.format(nontyped))
    if '|' in typed:
        types = typed.split('|')
        res = [disambiguate(t, nontyped) for t in types if disambiguate(t, nontyped)]
        if len(res) > 0:
            return res[0]
    if nontyped == "?":
        return typed
    if nontyped == "set<?>" and re.match(re.compile(r'set<.+>'), typed) is not None:
        return typed[4:-1]
    elif nontyped == "set<set<?>>" and re.match(re.compile(r'set<set.+>>'), typed) is not None:
        return typed[8:-2]
    else:
        return None


def get_ngram_probs(token_history, p_dict, possible_continuations):
    """
    return a probability vector over the next tokens given an ngram 'language model' of the
    the logical fforms. this is just a POC for generating plausible logical forms.
    the probability vector is the real model will come of course from the parameters of the
    decoder network.
    """
    probs = []
    prevprev_token = token_history[-2]
    prev_token = token_history[-1]
    token_counts = p_dict[0]
    bigram_counts = p_dict[1]
    trigram_counts = p_dict[2]
    for token in possible_continuations:
        probs.append(max(token_counts.get(token, 0) + 5 * bigram_counts.get((prev_token, token), 0) + \
                         9 * trigram_counts.get((prevprev_token, prev_token, token), 0), 1))
    return np.array(probs) / np.sum(probs)

class PartialProgram:
    """
    a class the represents an instance of seq2seq decoder, regardless of the decoding model itself.
    Each instance of PartialProgram is used for outputing one sequence of tokens (aka logical form).
    In a beam search approach, any partial program that is constracted is represented by another decoder instance
    (I think, not sure about that... @TODO)
    """

    def __init__(self, lt_mapping=None):

        self.vars = [c for c in "xyzwuv"]
        self.stack = ["bool"]
        self.token_seq = []
        self.vars_in_use = {}
        self.logprobs = []
        self.logical_tokens_mapping = lt_mapping
        self.stack_history = [tuple(["bool"])]


    def __repr__(self):
        return "Partial program:(log p : {0:.2f}, sequence : {1})".format(self.logprob, " ".join(self.token_seq))

    def __len__(self):
        return len(self.token_seq)

    def __getitem__(self, key):
        return self.token_seq[key]

    def __iter__(self):
        for s in self.token_seq:
            yield  s

    def __contains__(self, item):
        return item in self.token_seq

    def copy(self):
        pp_copy = PartialProgram(self.logical_tokens_mapping)
        pp_copy.vars = self.vars
        pp_copy.vars = self.vars.copy()
        pp_copy.stack = self.stack.copy()
        pp_copy.token_seq = self.token_seq.copy()
        pp_copy.vars_in_use = self.vars_in_use.copy()
        pp_copy.logprobs = self.logprobs.copy()
        pp_copy.stack_history = self.stack_history.copy()
        return pp_copy

    @property
    def logprob(self):
        return np.sum(self.logprobs)

    def get_possible_continuations(self):

        if len(self.stack) == 0:
            if self.token_seq[-1] == '<EOS>':
                return []
            return ["<EOS>"]  # end of decoding

        if len(self.token_seq) >= MAX_LENGTH:
            return []

        next_type = self.stack[-1]

        # the next token must have a return type that matches next_type or to be itself an instance of next_type
        # for example, if next_type is 'int' than the next token can be an integer literal, like '2', or the name
        # of a functions that has return type int, like 'count'.

        if next_type.startswith("bool_func"):
            # in that case there is no choice - the only valid token is 'lambda'
            if len(self.vars) == 0:
                return [] # cannot recover
            var = self.vars.pop(0)  # get a new letter to represent the var
            type_of_var = next_type[10:-1]
            if type_of_var == '?':
                raise TypeError("var in lambda function must be typed")
            # save the type of ver, and the current size of stack - the scope of the var depends on it.
            self.vars_in_use[var] = (TokenTypes(return_type=type_of_var, args_types=[], necessity=[]), len(self.stack)-1)
            next_token = 'lambda_{0}_:'.format(var)
            return [next_token]

        else:

            possible_continuations = [t for t, v in self.logical_tokens_mapping.items()
                                      if check_types(next_type, v.return_type)]
            possible_continuations.extend([var for var, (type_of_var, idx) in  self.vars_in_use.items()
                                           if check_types(next_type, type_of_var.return_type)])

            impossible_continuations = self.__get_impossible_continuations()
            return [c for c in possible_continuations if c not in impossible_continuations]



    def __get_impossible_continuations(self):


        impossible_continuations = []
        if self.token_seq and self.token_seq[-1] in self.logical_tokens_mapping:
            last = self.token_seq[-1]
            # if str.isdigit(last):
            # impossible_continuations.extend([str(i) for i in range(10)])
            last_return_type, last_args_types, _ = self.logical_tokens_mapping[last]
            if len(last_args_types) == 1 and last_args_types[0].startswith('set'):
                impossible_continuations.extend([t for t, v in self.logical_tokens_mapping.items()
                                                               if not v.args_types])
                if last!='count':
                    impossible_continuations.extend([t for t, v in self.vars_in_use.items()])

            if not last_args_types:
                impossible_continuations.extend([t for t, v in self.logical_tokens_mapping.items()
                                                              if not v.args_types and v.return_type == last_return_type])
            if len(self.stack)==3:
                impossible_continuations.extend([t for t, v in self.logical_tokens_mapping.items()
                                                if len(v.args_types)>1])

            if len(self.token_seq) >= 3 and all(tok == self.token_seq[-1] for tok in self.token_seq[-3:]):
                impossible_continuations.append(self.token_seq[-1])

            open_filter_scopes_begginnings = [start for start, end in self.filter_scopes() if not end]
            impossible_continuations.extend(
            [self.token_seq[t+1] for t in open_filter_scopes_begginnings if t<len(self.token_seq)-1])

            if last == 'equal':
                impossible_continuations.extend([t for t, v in self.logical_tokens_mapping.items()
                                                if not ('Color' in v.return_type or 'Shape' in v.return_type)])


        return impossible_continuations


    def add_token(self, token, logprob):
        if len(self.stack)==0:
            if token == '<EOS>':
                self.token_seq.append(token)
                return True
            else:
                raise ValueError("cannot add token {} to program: stack is empty".format(token))
        next_type = self.stack.pop()
        if token.startswith('lambda'):
            self.token_seq.append(token)
            self.stack.append('bool')
        else:
            if token in self.logical_tokens_mapping:
                token_return_type,  token_args_types, token_necessity = self.logical_tokens_mapping[token]
            elif token in self.vars_in_use:
                token_return_type, token_args_types, _ = self.vars_in_use[token][0]
            else:
                raise ValueError("cannot add token {} to program: not a known function or var".format(token))
            t = disambiguate(next_type, token_return_type)
            s = disambiguate(token_return_type, next_type)
            if s is not None:
                # update jokers in stack:
                for i in range(len(self.stack) - 1, -1, -1):
                    if '?' in self.stack[i]:
                        self.stack[i] = self.stack[i].replace('?', s)
                    else:
                        break

            self.token_seq.append(token)
            args_to_stack = [arg if t is None else arg.replace('?', t) for arg in
                             token_args_types[::-1]]
            self.stack.extend(args_to_stack)


        for var, (type_of_var, idx) in [kvp for kvp in self.vars_in_use.items()]:
        # after popping the stack, check whether one of the added variables is no longer in scope.
            if len(self.stack) <= idx:
                if var in self.token_seq:
                    del self.vars_in_use[var]
                else:
                    return False
                break


        bool_scopes = [" ".join(self.token_seq[start : end]) for start, end in self.boolean_scopes() if end]
        if len(set(bool_scopes)) < len(bool_scopes):
            return False

        self.stack_history.append(tuple(self.stack))
        self.logprobs.append(logprob)

        return True

    def boolean_scopes(self):
        scopes = []
        for i in range(1, len(self.stack_history)):
            if self.stack_history[i] and self.stack_history[i][-1] == 'bool':
                end_of_exp = ([j for j in range (i +1 , len(self.stack_history)) if len(self.stack_history[j])
                               < len(self.stack_history[i])])
                if not end_of_exp:
                    scopes.append((i, None))
                else:
                    scopes.append((i, min(end_of_exp)))
        return scopes

    def filter_scopes(self):
        scopes = []
        for i in range(len(self.token_seq)):
            if self.token_seq[i]  == 'filter':
                end_of_exp = ([j for j in range (i +1 , len(self.stack_history)) if len(self.stack_history[j])
                               < len(self.stack_history[i])])
                if not end_of_exp:
                    scopes.append((i, None))
                else:
                    scopes.append((i, min(end_of_exp)))
        return scopes


def get_formalized_sentence(sentence):
    '''
    same as the one below but only for a sentence
    :param sentence: 'there is a yellow item'
    :return: 'there is a T_COLOR item'
    '''

    # building replacements "dictionary" (it is actually a list of tuples)
    formalization_file = os.path.join(definitions.DATA_DIR, 'sentence-processing', 'formalized words.txt')
    dict = load_dict_from_txt(formalization_file)
    for i in range(2,10):
        dict[str(i)] = 'T_INT'
    dict["1"] = 'T_ONE'
    dict["one"] = 'T_ONE'
    manualy_chosen_replacements = sorted(dict.items(), key = lambda x : sentence.find(x[0]))
    manualy_chosen_replacements = [(" {} ".format(entry[0]), " {} ".format(entry[1])) for entry in manualy_chosen_replacements]

    formalized_sentence = " {} ".format(sentence)  # pad with whitespaces
    used_reps = []
    # reminder: exp = yellow, replacement = T_COLOR
    for exp, replacement in manualy_chosen_replacements:
        if replacement not in used_reps and exp in formalized_sentence:
            formalized_sentence = formalized_sentence.replace(exp, replacement)
            used_reps.append(replacement)
        elif replacement in used_reps and exp in formalized_sentence and (replacement.rstrip() + '_1 ') not in used_reps:
            replacement = replacement.rstrip() + '_1 '
            formalized_sentence = formalized_sentence.replace(exp, replacement)
            used_reps.append(replacement)
        else:
            replacement = replacement.rstrip() + '_2 '
            formalized_sentence = formalized_sentence.replace(exp, replacement)

    formalized_sentence = formalized_sentence.strip()

    return formalized_sentence


def get_programs_for_sentence_by_pattern(sentence, patterns_dict):
    '''
    :param sentence: english sentence, str
    :param patterns_dict: dict of english formalized sents and formalized logical forms, {str: str}
    :return: a *string* that is a suggested program based on the dict
    '''
    words = sentence.split()
    formalized_sent = get_formalized_sentence(sentence)
    formalized_words = formalized_sent.split()

    matching_patterns = patterns_dict.get(formalized_sent, {})

    for i, word in enumerate(words):
        if word == 'at' and (words[i+1] == 'most' or words[i+1] == 'least'):
            words[i:i+2] = [' '.join(words[i:i+2])]


    suggested_decodings = []
    for prog, acc_reward in sorted(matching_patterns.items(), key = lambda item : item[1][0], reverse=True):
        token_seq = prog.split()

        for i, _ in enumerate(words):
            try:
                if words[i] == formalized_words[i]:
                    continue
            except IndexError:
                continue

            for j, token in enumerate(token_seq):
                if formalized_words[i] in token and numbers_contained(formalized_words[i]) == numbers_contained(token)\
                        and words[i] in log_dict:
                            token_seq[j] =  (token_seq[j]).replace(formalized_words[i],  log_dict[words[i]])

        # return token_seq
        token_str = ' '.join(token_seq)
        suggested_decodings.append(token_str)
    return suggested_decodings


def get_formlized_sentence_and_decoding(sentence, program, patterns_dict):
    '''
    :param sentence: 'there is a yellow item'
    :param program: exist filter ALL_ITEMS lambda_x_: is_yellow x
    :return:
            'there is a T_COLOR item', {'exist filter ALL_ITEMS lambda_x_: is_T_COLOR x': None}
            and adding both to patterns_dict
    '''

    if get_formalized_sentence(sentence) in patterns_dict:
        return get_formalized_sentence(sentence), patterns_dict[get_formalized_sentence(sentence)]

    # building replacements "dictionary" (it is actually a list of tuples)
    formalization_file = os.path.join(definitions.DATA_DIR, 'sentence-processing', 'formalized words.txt')
    dict = load_dict_from_txt(formalization_file)
    for i in range(2,10):
        dict[str(i)] = 'T_INT'
    dict["1"] = 'T_ONE'
    dict["one"] = 'T_ONE'
    manualy_chosen_replacements = sorted(dict.items(), key = lambda x : sentence.find(x[0]))
    manualy_chosen_replacements = [(" {} ".format(entry[0]) , " {} ".format(entry[1])) for entry in manualy_chosen_replacements]
    formalized_sentence = " {} ".format(sentence)  # pad with whitespaces
    formalized_program = " {} ".format(program)  # pad with whitespaces

    temp_dict = {}
    for exp, replacement in manualy_chosen_replacements:
        if exp in formalized_sentence and replacement not in temp_dict.values():
            temp_dict[exp] = replacement
        elif exp in formalized_sentence and replacement in temp_dict.values() and (replacement.rstrip() + '_$ ') not in temp_dict.values():
            temp_dict[exp] = replacement.rstrip() + '_$ '
        elif exp in formalized_sentence and replacement in temp_dict.values() and (replacement.rstrip() + '_$ ') in temp_dict.values():
            temp_dict[exp] = replacement.rstrip() + '_2 '
    temp_dict = [(k, temp_dict[k]) for k in temp_dict]

    for exp, replacement in temp_dict:
        formalized_sentence = formalized_sentence.replace(exp, replacement)
    formalized_sentence = formalized_sentence.strip()
    formalized_sentence = formalized_sentence.replace('$', '1')


    for exp, replacement in temp_dict:
        formalized_program = formalized_program.replace(log_dict[exp.strip()], replacement.strip())
    formalized_program = formalized_program.strip()
    formalized_program = formalized_program.replace('$', '1')

    if formalized_sentence not in patterns_dict:
        patterns_dict[formalized_sentence] = {}
    patterns_dict[formalized_sentence][formalized_program] = None

    return formalized_sentence, {formalized_program: None}


def numbers_contained(string):

    nums = []
    for char in string:
        if char.isdigit():
            nums.append(char)
    return nums


def update_programs_cache(cached_programs, sentence, prog, n_correct, n_incorrect):
    '''
    :param sentence: 'there is a yellow item'
    :param program: exist filter ALL_ITEMS lambda_x_: is_yellow x
    :return:
            'there is a T_COLOR item', {'exist filter ALL_ITEMS lambda_x_: is_T_COLOR x': None}
            and adding both to patterns_dict
    '''

    formalized_sentence = get_formalized_sentence(sentence)
    if formalized_sentence not in cached_programs:
        cached_programs[formalized_sentence] = {}
    matching_cached_patterns = cached_programs.get(formalized_sentence)

    # building replacements "dictionary" (it is actually a list of tuples)
    formalization_file = os.path.join(definitions.DATA_DIR, 'sentence-processing', 'formalized words.txt')
    dict = load_dict_from_txt(formalization_file)
    for i in range(2,10):
        dict[str(i)] = 'T_INT'
    dict["1"] = 'T_ONE'
    dict["one"] = 'T_ONE'
    manualy_chosen_replacements = sorted(dict.items(), key = lambda x : sentence.find(x[0]))
    manualy_chosen_replacements = [(" {} ".format(entry[0]) , " {} ".format(entry[1])) for entry in manualy_chosen_replacements]
    formalized_sentence = " {} ".format(sentence)  # pad with whitespaces
    formalized_program = " {} ".format(" ".join(prog.token_seq))  # pad with whitespaces

    temp_dict = {}
    for exp, replacement in manualy_chosen_replacements:
        if exp in formalized_sentence and replacement not in temp_dict.values():
            temp_dict[exp] = replacement
        elif exp in formalized_sentence and replacement in temp_dict.values() and (replacement.rstrip() + '_$ ') not in temp_dict.values():
            temp_dict[exp] = replacement.rstrip() + '_$ '
        elif exp in formalized_sentence and replacement in temp_dict.values() and (replacement.rstrip() + '_$ ') in temp_dict.values():
            temp_dict[exp] = replacement.rstrip() + '_2 '
    temp_dict = [(k, temp_dict[k]) for k in temp_dict]

    for exp, replacement in temp_dict:
        formalized_sentence = formalized_sentence.replace(exp, replacement)
    formalized_sentence = formalized_sentence.strip()
    formalized_sentence = formalized_sentence.replace('$', '1')


    for exp, replacement in temp_dict:
        if exp.strip() in log_dict: # TODO figure out what's wrong here
            formalized_program = formalized_program.replace(log_dict[exp.strip()], replacement.strip())
    formalized_program = formalized_program.strip()
    formalized_program = formalized_program.replace('$', '1')

    if formalized_program not in matching_cached_patterns:
        matching_cached_patterns[formalized_program] = [0,0]

    matching_cached_patterns[formalized_program][0] + n_correct
    matching_cached_patterns[formalized_program][1] + n_incorrect

    if (matching_cached_patterns[formalized_program][0] + 1) / (matching_cached_patterns[formalized_program][1]
                                                          +0.1) < 3:
        del matching_cached_patterns [formalized_program]
    return

def get_ands(pp : PartialProgram):
    ind = -1
    results = []
    while True:
        if 'AND' in pp[ind+1:]:
            ind = pp.token_seq.index('AND', ind+1)
            stack_state_begin = len(pp.stack_history[ind])
            try:
                mid = min([i for i in range (ind +1 , len(pp)) if len(pp.stack_history[i]) == stack_state_begin])

                fin = min([i for i in range (mid +1 , len(pp)+1) if len(pp.stack_history[i]) < stack_state_begin])
            except:
                pass
            results.append((ind, mid, fin))
        else:
            break
    decode_with_signs = []
    if not results:
        return [], " ".join(pp.token_seq)
    if len(results)>1:
        print()
    inds, mids, fins = zip(*results)
    #assert len(inds) + len(mids) + len(fins) == len(set(inds+mids+fins))
    for i, tok in enumerate(pp):
        if i in mids:
            decode_with_signs.append(',')
        decode_with_signs.append(tok)
        if i in inds:
            decode_with_signs.append('(')
        if i+1 in fins:
            decode_with_signs.append(')')
    return results, " ".join(decode_with_signs)