"""
References:
- J. Dedina and H. C. Nusbaum. "PRONOUNCE: a program for pronunciation by
  analogy." Comput. Speech Lang. 5(1), 1991, pp. 55-64.
- Y. Marchand and R. I. Damper. "A multistrategy approach to improving
  pronunciation by analogy." Comput. Linguist. 26(2), 2000, pp. 196-219.
- Y. Marchand and R. I. Damper. "Can syllabification improve pronunciation by
  analogy of English?" Nat. Lang. Eng. 13(1) 2006, pp. 1-24.
"""

import os
from collections import Counter, deque
from operator import itemgetter
from config import cmudict_path, nettalk_path


class SyllableCounter(object):
    def __init__(self, sba_lexicon_path=nettalk_path, cmudict_path=cmudict_path):
        self._load_data(sba_lexicon_path, cmudict_path)

    def _load_data(self, sba_lexicon_path, cmudict_path):
        self.lexicon = []
        self.counter = {}

        with open(sba_lexicon_path, 'r') as f, open(cmudict_path, 'r') as g:
            sba_lexicon = f.read().splitlines()
            cmudict = g.read().splitlines()

        for line in sba_lexicon:
            if not line or line.startswith('#'):
                continue
            line = line.split()
            word = line[0]
            syll = line[2]
            count = 0

            hyphenated_word = ''
            for i, ch in enumerate(word):
                if i < len(word)-1 and syll[i] != '>' and syll[i+1] != '<':
                    hyphenated_word += ch + '-'
                    count += 1
                else:
                    hyphenated_word += ch + '*'

            self.lexicon.append('#{}#'.format(hyphenated_word[:-1]))
            self.counter[word] = count + 1

        for line in cmudict:
            if not line or line.startswith(';;;'):
                continue
            word = line.split(None, 1)[0].lower()
            count = sum(ch.isdigit() for ch in line)

            if word.endswith(')'):
                continue

            if word not in self.counter or self.counter[word] < count:
                self.counter[word] = count

    def _sba(self, input):
        # Node data class
        class data(object):
            def __init__(self):
                self.outputs = Counter() # Set of arcs going out
                self.sinputs = [] # Set of arcs coming in, filled by BFS
                self.distance = float('inf') # From origin, filled by BFS

        # Format input
        input = '#{}#'.format(input.replace('', '*')[1:-1])

        # Pronunciation lattice
        lattice = {('#', 0): data(), ('#', len(input)-1): data() }

        # Substring matcher and lattice builder
        substring = []
        for entry in self.lexicon:
            for offset in range(-len(input)+3, len(entry)-2):
                for i in range(max(0, -offset), min(len(input), len(entry)-offset)):
                    if input[i] == entry[i+offset] or (input[i] == '*' and entry[i+offset] == '-'):
                        substring.append((entry[i+offset], i))
                    else:
                        for i, node in enumerate(substring):
                            string = ''
                            if node not in lattice:
                                lattice[node] = data()
                            for j in range(i+1, len(substring)):
                                string += substring[j][0]
                                arc = (substring[j], string[:-1])
                                lattice[node].outputs[arc] += 1
                        substring.clear()

                for i, node in enumerate(substring):
                    string = ''
                    if node not in lattice:
                        lattice[node] = data()
                    for j in range(i+1, len(substring)):
                        string += substring[j][0]
                        arc = (substring[j], string[:-1])
                        lattice[node].outputs[arc] += 1

        # Decision function 1: get shortest path(s)
        queue = deque([('#', 0)])
        lattice[('#', 0)].distance = 0
        while queue:
            node = queue.popleft()
            for out_arc in lattice[node].outputs:
                adjacent = out_arc[0]
                in_arc = (node, out_arc[1], lattice[node].outputs[out_arc])
                if lattice[node].distance + 1 < lattice[adjacent].distance:
                    queue.append(adjacent)
                    lattice[adjacent].distance = lattice[node].distance + 1
                    lattice[adjacent].sinputs.append(in_arc)
                elif lattice[node].distance + 1 == lattice[adjacent].distance:
                    lattice[adjacent].sinputs.append(in_arc)
        queue.clear()

        # Decision function 2: score by strategy
        # PF = product, SDPS = standard deviation, WL = weak link
        # Calculate scores
        paths = []
        def dfs(node, path, arcs):
            if node == ('#', 0):
                pf, sdps, wl = 1, 0, float('inf')
                mean = sum(arcs)/len(arcs)
                for arc in arcs:
                    pf *= arc
                    sdps += (arc-mean)**2
                    wl = min(wl, arc)
                sdps /= len(arcs)

                paths.append((path, pf, sdps, wl))
                return
            if not lattice[node].sinputs:
                return

            path = node[0] + path
            for arc in lattice[node].sinputs:
                _arcs = arcs[:]
                _arcs.append(arc[2])
                dfs(arc[0], arc[1]+path, _arcs)

        dfs(('#', len(input)-1), '', [])
        if not paths:
            print('UserWarning: No syllabification found')
            return None

        # Assign point values
        scores = {path[0]: 0 for path in paths}
        for s in range(1, 4):
            ranking = sorted(paths, key=itemgetter(s), reverse=True)
            rank, cand, cval = len(paths), 0, ranking[0][s]

            for i, path in enumerate(ranking):
                if path[s] < cval:
                    points = rank - (cand-1)/2
                    for t in ranking[i-cand:i]:
                        scores[t[0]] += points
                    rank -= 1
                    cand, cval = 1, path[s]
                else:
                    cand += 1

            points = rank - (cand-1)/2
            for t in ranking[-cand:]:
                scores[t[0]] += points

        shortest_path = max(scores.items(), key=itemgetter(1))[0][:-1]
        n_syllables = shortest_path.count('-') + 1
        return n_syllables, shortest_path

    def get_syllable_count(self, word):
        if word in self.counter:
            return self.counter[word]
        else:
            return self._sba(word)[0]