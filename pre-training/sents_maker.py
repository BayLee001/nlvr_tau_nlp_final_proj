from copy import deepcopy
import pickle

# def dim_caller(words):
#     shape = []
#     for word in words:
#         if 'COLOR' in word or 'SHAPE' in word or 'LOC' in word or 'QUANTITY' in word:
#             shape.append(3)
#         elif 'INT' in word:
#             shape.append(6)
#         else:
#             raise NameError('oopsy')

fsents = open(r'temp_sents.txt')

colors = ['yellow', 'blue', 'black']
wlocs = ['top', 'bottom', 'base']
llocs = ['top', 'bottom', 'bottom']
locs = [('top', 'top'), ('bottom', 'bottom'), ('base', 'bottom')]
ints = ['2', '3', '4', '5', '6', '7']
shapes = ['triangle', 'circle', 'square',]
wquants = ['exactly', 'at least', 'at most']
lquants = ['equal_int', 'ge', 'le']
quants = [('exactly', 'equal_int'), ('at least', 'ge'), ('at most', 'le')]
ones = ['1']

sents = []
for line in fsents:
    tempsents = {}
    if line.startswith('@'):
        engsent = line[2:].rstrip()
        # engwords = engsent.split()
    elif line.startswith('~'):
        logsent = line[2:].rstrip()
        sents.append([engsent, logsent])
    else:
        continue

print('beginning with ', len(sents), 'sentences')

# newsents = sents
oldsents = []
# while newsents != []:
while oldsents != sents:
    oldsents = deepcopy(sents)
    for sent in sents:
        engsent = sent[0]
        logsent = sent[1]
        engwords = engsent.split()
        for i, word in enumerate(engwords):
            if word == word.upper() and word != '1' and word not in ints:
                sents.remove(sent)
                if 'COLOR' in word:
                    for color in colors:
                        newlog = logsent.replace(word, color)
                        neweng = engwords
                        neweng[i] = color
                        neweng = ' '.join(neweng)
                        sents.append([neweng, newlog])
                elif 'SHAPE' in word:
                    for shape in shapes:
                        newlog = logsent.replace(word, shape)
                        neweng = engwords
                        neweng[i] = shape
                        neweng = ' '.join(neweng)
                        sents.append([neweng, newlog])
                elif 'INT' in word:
                    for inty in ints:
                        newlog = logsent.replace(word, inty)
                        neweng = engwords
                        neweng[i] = inty
                        neweng = ' '.join(neweng)
                        sents.append([neweng, newlog])
                elif 'LOC' in word:
                    for loc in locs:
                        newlog = logsent.replace(word, loc[1])
                        neweng = engwords
                        neweng[i] = loc[0]
                        neweng = ' '.join(neweng)
                        sents.append([neweng, newlog])
                elif 'QUANTITY' in word:
                    for quant in quants:
                        newlog = logsent.replace(word, quant[1])
                        neweng = engwords
                        neweng[i] = quant[0]
                        neweng = ' '.join(neweng)
                        sents.append([neweng, newlog])
                # elif 'ONE' in word:
                #     for one in ones:
                #         newlog = logsent
                #         neweng = engwords
                #         neweng[i] = one
                #         neweng = ' '.join(neweng)
                #         sents.append([neweng, newlog])
                break

    print('so far ', len(sents), 'sentences')

print('done! ', len(sents), 'sentences')

file = open('sents_for_pretain', 'wb')
pickle.dump(sents, file)
file.close()
