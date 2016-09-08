# ffb-analytics
Draft Tool for Fantasy Football Analytics

For now, the algorthim works by starting a statically defined order of positions you intend to draft, then doing the following
    -calculate total value by chosing each pick evaluating for value, based on ADP choose the best expected available player
    -rearranging the order of positions by choosing two or more differing positions and rearranging them
    -re-evaluating for value, keep the better of the two and continue

To use, do the following:
1) Export with settings for your league to FFA-rankings.csv
        from http://apps.fantasyfootballanalytics.net/projections
2) Set the following variables for your team / league settings
    players_per_team
    num_teams
    initial_pick

3) Set a naive starting order (order of picks), quantity of positions will stay the same, but will rearranged to optimize for points
naive_starter_order = ['RB', 'WR', 'RB', 'WR', 'QB', 'TE', 'WR', 'RB', 'WR', 'DST', 'WR', 'WR', 'QB', 'RB', 'K']

4) Decide live_mode or non live_mode (analytics mode)... live mode assumes that you have the top choice for the next pick
live_mode = True

5) Choose a swap order... for each value in this array the algorithm attempts to rearrange every subset of positions
    in every reasonable permutation.

    More details about swap order
    # This defines the number of positions attempted to swap at one time, if the value is set to two, it evaluates
    #  all meaningful scenarios where two positions are chosen in opposite order.  If the value is three or more, it will
    #  attempt to choose all meaningful sets of three positions, rearrange into all permutations
    #  to determine if there's a more valuable order
    swap_order = [2, 2, 3, 2, 3, 2]

6) Run the program to generate output

7) If running in live mode,
    -populate exclude-names.txt, with players already drafted by other teams
    -populate my-team.txt, with players on my team
    -re execute main before each pick (swap order may need to be more conservative for live mode as aggressive swaps (such as 4+) will take more time
    -the first line in the file should be the header 'playername', each player name should be followed by a new line see the .example files
        -a python fuzzy string matching algorithm is used to match resolve typos, the threshold has not yet been tested so try to be as accurate as possible.