import numpy as np
import pandas as pd
import itertools
from fuzzywuzzy import fuzz, process
import difflib
from collections import OrderedDict
import operator


class Picker:
    def __init__(self, df, starter_count_map):
        self.all_combinations = []
        self.debug_mode = False
        self.df = df
        # TODO: would be nice to have a flex option for starters
        self.starter_count_map = starter_count_map
        self.count_swaps = 0
        self.selection = None
        self.already_picked_df = None
        self.lookup_previously_calculated = {}
        # Using two different ranking criteria creates poor results, figure out a way to generate a consistent
        #   value measurement (possibly by combining points, risk, and upside)
        self.score_column = 'points'
        self.rank_column = 'overallECR'
        self.rank_high_better = False

    def calc_snake_pick_numbers(self, num_teams, players_per_team, initial_pick):
        round = 1
        picks = []
        while round <= players_per_team:
            end_of_last_round = (round - 1) * num_teams
            if round % 2 == 1:
                cur_pick = end_of_last_round + initial_pick
            else:
                cur_pick = end_of_last_round + 1 + num_teams - initial_pick
            round += 1
            picks.append(cur_pick)
        return picks

    def best_player_index(self, position, pick_num, excluding=None):
        if self.debug_mode:
            print 'pick_player({0}, {1})'.format(position, pick_num)
        f = (self.df['adp'] > pick_num) & (self.df['playerposition'] == position) & (~ (self.df.index.isin(excluding)))
        new_df = self.df[f]
        if self.rank_high_better:
            return new_df[self.rank_column].idxmax()
        else:
            return new_df[self.rank_column].idxmin()

                # return new_df['overallECR'].idxmin()

    def pick_all(self, ordered_positions, remaining_picks):
        # Iterate through each position in order, pick the best player for that pick (number)
        key = str(ordered_positions)
        if key in self.lookup_previously_calculated:
            return self.lookup_previously_calculated[key]
        picked_players = []
        pick_index = 0
        for pos in ordered_positions:
            ap = []
            if self.already_picked_df is not None:
                ap.extend(self.already_picked_df.index.tolist())
            if picked_players is not None:
                ap.extend(picked_players)
            player_index = self.best_player_index(pos, remaining_picks[pick_index], excluding=ap)
            picked_players.append(player_index)
            pick_index += 1
        team = self.df.ix[picked_players]
        if self.already_picked_df is not None:
            team = pd.concat([self.already_picked_df, team])
        score = self.score_team(team)
        selection = PlayerSelection(team, ordered_positions, score)
        self.lookup_previously_calculated[key] = selection
        return selection

    def score_team(self, selected_players):
        ###
        # TODO: put serious thought into this method
        # This method was an afterthought, but may be the most essential component in a highly optimized draft.
        # As it stands, the first bench player chosen at each position adds huge value, whereas the second is a penalty.
        #
        # Ideally we would like to evaluate each player according to the final value they add to the team.  If we can do
        #  so in a way that is accurate, we should be able to experiment with a path traversal as opposed to swapping
        #  positions.  Path traversal with a good heuristic would significantly optimize the way we evaluate
        #  permutations of players and would result in a faster and more optimized draft.  Additionally, this would
        #  free us to evaluate teams with different quantities of players as opposed to a predefined quantity at
        #  each position.
        #
        ###
        # TODO: account for risk and upside (especially with backups)

        total_points = 0
        for pos, num_starters in self.starter_count_map.iteritems():
            f = selected_players['playerposition'] == pos
            pos_df = selected_players[f]
            if len(pos_df) == 0:
                continue
            pos_df = pos_df.sort_values(by=self.score_column, ascending=False)
            starters = pos_df[:num_starters]
            backups = pos_df[num_starters:]


            if len(backups.index) == 0:
                s_avg = .8 * starters[self.score_column].mean()
                b_avg = 0
            else:
                s_avg = .7 * starters[self.score_column].mean()
                # print type(backups[self.score_column].tolist())
                weighted_backup_pts = []
                weight = 5
                step = 1
                for backups_pts in backups[self.score_column].tolist():
                    weighted_backup_pts.extend([backups_pts] * weight)

                weighted_avg = sum(weighted_backup_pts) / len(weighted_backup_pts)
                b_avg = .3 * weighted_avg
                # print '{} : avg={} '.format(weighted_backup_pts, weighted_avg)

            total_points += (s_avg + b_avg) * num_starters
        return total_points

    # Given a previous position_order, an array of selected positions, and a minimum index...
    # choose a set of indexes with different positions, attempt to rearrage them into every new permutation
    def shuffler(self, position_order, indexes_to_swap, picks, min_index=0, max_pos_swap=2):
        selection = self.pick_all(position_order, picks)
        if self.selection is None:
            self.selection = selection
        position_order = position_order

        for cur_min_index in range(min_index, len(position_order)):
            selected_index = self.next_non_matching(position_order, indexes_to_swap, cur_min_index)
            if selected_index is not None:
                # theres a swappable position
                cur_idx_to_swap = indexes_to_swap[:]
                cur_idx_to_swap.append(selected_index)
                if len(cur_idx_to_swap) >= max_pos_swap:
                    # we've reached the max on swappable positions, evaluate
                    # print 'considering swap combo = {}'.format(cur_idx_to_swap)
                    for p in itertools.permutations(cur_idx_to_swap):
                        # TODO: swap, score, choose winner
                        p_list = list(p)
                        p_list_sorted = p_list[:]
                        p_list_sorted.sort()
                        if p_list == p_list_sorted:
                            # optimization, exclude permutations which don't move anything
                            continue
                        # print '  considering swap permutation = {}'.format(p)
                        self.count_swaps += 1
                        if self.count_swaps % 1000 == 0:
                            print 'swap attempts: {}'.format(self.count_swaps)
                            print '  unique permutations cached: {}'.format(len(self.lookup_previously_calculated))

                        new_pos_order = position_order[:]
                        for i in range(0, len(p)):
                            from_idx = cur_idx_to_swap[i]
                            to_idx = p[i]
                            new_pos_order[to_idx] = position_order[from_idx]

                        new_selection = self.pick_all(new_pos_order, picks)
                        if new_selection.score > self.selection.score:
                            print '----- SWAPPING INDEXES {} ------'.format(p)
                            print '  INSTEAD OF: order={} score={}'.format(self.selection.position_order_arr, self.selection.score)
                            self.selection = new_selection
                            print '  SELECTED  : order={} score={}'.format(self.selection.position_order_arr, self.selection.score)
                            print '  after {} swap attempts'.format(self.count_swaps)

                else:
                    # recursively attempt to choose another position, so that we can reach the max num positions
                    self.shuffler(position_order, cur_idx_to_swap, picks, min_index=cur_min_index + 1
                                                  , max_pos_swap=max_pos_swap)

    # Given a previous position_order, an array of selected positions, and a minimum index...
    #   return the index of the first position which has not already been selected, or None if all remaining positions
    #   are already contained in the already selected positions
    def next_non_matching(self, position_order, selected_indexes, minimum_index):
        for i in range(minimum_index, len(position_order)):
            already_selected_positions = [position_order[j] for j in selected_indexes]
            if position_order[i] not in already_selected_positions:
                # print 'DEBUG: pos {} not in {}'.format(position_order[i], already_selected_positions)
                return i
        return None


class PlayerSelection:
    # Encapsulates the players chosen as a df, the position order as an array, and the score of the selection
    def __init__(self, picked_players_df, position_order_arr, score):
        self.picked_players_df = picked_players_df
        self.position_order_arr = position_order_arr
        self.score = score

# TODO: integrate into PlayerSelection as alternate way to construct
def player_selection_from_df(picker, picks):
    team = picks
    score = picker.score_team(team)
    ordered_positions = picks['playerposition'].tolist()
    return PlayerSelection(team, ordered_positions, score)

class StringCompare:
    def __init__(self, choices):
        self.choices = choices

    # TODO: test threshold with misspellings
    def matches(self, name, fuzzy_threshold=90):
        best_match = process.extractOne(name, self.choices)
        # print 'best match = {}'.format(best_match)
        if best_match is None:
            return False
        result = best_match[1] > fuzzy_threshold
        if result:
            print '{} matched {}'.format(name, result)
            self.choices.remove(best_match[0])
        return result

# TODO: the following variables should all be params to the app
# Live mode assumes all players who are not in the exclude_names.txt file are available for the next pick
live_mode = True
players_per_team = 16
num_teams = 12
initial_pick = 5

# don't wrap on print
pd.set_option('expand_frame_repr', False)

df = pd.read_csv('../../data/FFA-rankings.csv', usecols=np.arange(1, 23))
# for some reason they print nulls as strings when exporting, clean that up
df = df.replace(['null'], [None])
df = df.apply(lambda x: None if x is 'null' else x)
# convert numeric string values to actual numbers
df = df.apply(lambda x: pd.to_numeric(x, errors='ignore'))
# these columns may be useful in the future, for now they just make it difficult to read dataframe output
df.drop(['player','position','team','playerteam','vor','actualPoints','cost','salary','auctionValue','sleeper', 'dropoff', 'adpdiff', 'risk'],inplace=True,axis=1)
print "Loaded data with {0} rows".format(str(len(df.index)))

my_team_df = None

min_swappable_index = 0
my_team_len = 0
my_team_list = pd.read_csv('../../data/my_team.txt')['playername'].tolist()
if my_team_list is not None and len(my_team_list) > 0:
    df['playername'] = df['playername'].apply(lambda x:  x.lower());
    sc = StringCompare(my_team_list)
    my_team_df = df[df.apply(lambda x: sc.matches(x['playername']), axis=1)]
    min_swappable_index = len(my_team_list)
    print my_team_df
    my_team_len = len(my_team_df.index)

exclude_list = pd.read_csv('../../data/exclude_names.txt')['playername'].tolist()
exclude_list.extend(my_team_list)
print 'excluding {}'.format(exclude_list)
sc = StringCompare(exclude_list)
# TODO: this is probably unnecessary as fuzzywuzzy seems to ignore case
df['playername'] = df['playername'].apply(lambda x:  x.lower());
# check to see whether the player

f = df.apply(lambda x: sc.matches(x['playername']), axis=1)
excluded_df = df[f]
print '-----------------excluded players ---------------'
print excluded_df
df = df[~f]

starter_count_map = OrderedDict([('TE', 1), ('QB', 1), ('WR', 3), ('RB', 2), ('DST', 1), ('K', 1)])
picker = Picker(df, starter_count_map)
picks = picker.calc_snake_pick_numbers(num_teams, players_per_team, initial_pick)

if my_team_len > 0:
    for i in range(0, min(my_team_len + 1, players_per_team)):
        picks[i] = 1
print 'picks: {}'.format(picks)

# TODO: why doesn't the optimizer find a good order given a poorly optimized starting order
# naive_starter_order = ['K', 'QB', 'RB', 'WR', 'DST', 'WR', 'WR', 'RB', 'RB', 'RB', 'TE', 'QB', 'WR', 'WR', 'WR']
conventional_wisdom = ['RB', 'WR', 'RB', 'WR', 'QB', 'TE', 'WR', 'RB', 'WR', 'DST', 'WR', 'WR', 'QB', 'RB', 'K']
naive_starter_order = conventional_wisdom
if my_team_df is not None:
    for pos in my_team_df['playerposition'].tolist():
        naive_starter_order.remove(pos)
    picker.already_picked_df = my_team_df
# naive_starter_order = ['QB', 'RB', 'WR', 'RB']

print 'Evaluating {} positions: {}'.format(len(naive_starter_order), naive_starter_order)

# This defines the number of positions attempted to swap at one time, if the value is set to two, it evaluates
#  all meaningful scenarios where two positions are chosen in opposite order.  If the value is three or more, it will
#  attempt to choose all meaningful sets of three positions, derive all permutations, and attempt to rearrange them
#  in every order to determine if there's a more valuable order
swap_order = [2, 2, 3, 2, 3, 2]
# swap_order = [2]

for max_swaps in swap_order:
    picker.shuffler(naive_starter_order, [], picks, max_pos_swap=max_swaps)
    print '\n\n'
    print '---BEST Selection up to this point--- with score of {}'.format(picker.selection.score)
    print picker.selection.picked_players_df
    if live_mode:
        pos = picker.selection.position_order_arr[my_team_len]
        print '---TOP PROSPECTS FOR POS {}---'.format(pos)
        # filter already on my team players
        avail_players_df = df[~(df.index.isin(my_team_df.index.tolist()))]
        pos_df = avail_players_df[avail_players_df['playerposition'] == pos]
        if picker.rank_high_better:
            print pos_df.nlargest(10, picker.rank_column)
        else:
            print pos_df.nsmallest(10, picker.rank_column)
        print '\n'



# Questions:
# 1) best way to aggregate single rows into a df
# 1A) how to use multiple index values to filter a df
# 1B) how to combine multiple series into a df
# 2) how to choose the row with the minimum value in a specific column
# 3) performance of multiple dfs vs array type performance
# 4) How to use min/max to create statistical fuzz

