import requests
import pandas as pd
import concurrent.futures

API_URL = 'https://fantasy.premierleague.com/api/bootstrap-static/'


def load_data():
    """Fetch bootstrap data from FPL API."""
    data = requests.get(API_URL)
    return data


def load_player_history(element_id):
    """Load historical data for a specific player."""
    url = f'https://fantasy.premierleague.com/api/element-summary/{element_id}/'
    r = requests.get(url)
    json = r.json()
    json_history_df = pd.DataFrame(json['history'])
    week_history_df = json_history_df[['element', 'round', 'total_points', 'defensive_contribution', 'bonus']]
    return week_history_df


def load_history(elements_df, progress_callback=None):
    """Load history for all players with optional progress callback."""
    total = len(elements_df)
    completed = 0
    
    def load_with_progress(element_id):
        nonlocal completed
        result = load_player_history(element_id)
        completed += 1
        if progress_callback:
            progress_callback(completed, total)
        return result
    
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = [executor.submit(load_with_progress, element_id) for element_id in elements_df.id]
        all_history_df = pd.concat([future.result() for future in concurrent.futures.as_completed(futures)])
    return all_history_df


def prepare_data(api_data):
    """
    Process raw API data into clean dataframes.
    
    Returns:
        tuple: (slim_elements_df, all_history_df, elements_types_df, teams_df)
    """
    json = api_data.json()
    
    # Load raw dataframes
    elements_df = pd.DataFrame(json['elements'])
    elements_types_df = pd.DataFrame(json['element_types'])
    teams_df = pd.DataFrame(json['teams'])
    
    # Filter to only players with minutes played
    elements_df = elements_df[elements_df.minutes > 0].reset_index(drop=True)
    
    # Prepare slim elements dataframe
    slim_elements_df = elements_df[['id', 'first_name','second_name','team','element_type',
                                     'selected_by_percent','now_cost','minutes','transfers_in',
                                     'value_season','total_points', 'points_per_game']].copy()
    slim_elements_df['position'] = slim_elements_df.element_type.map(
        elements_types_df.set_index('id').singular_name)
    slim_elements_df['team_name'] = slim_elements_df.team.map(teams_df.set_index('id').name)
    slim_elements_df['value'] = slim_elements_df.value_season.astype(float)
    slim_elements_df['price'] = slim_elements_df.now_cost / 10
    slim_elements_df['selected_by_percent'] = slim_elements_df.selected_by_percent.astype(float)
    slim_elements_df['player'] = slim_elements_df.first_name + " " + slim_elements_df.second_name
    
    # Convert to category dtype for faster filtering
    slim_elements_df['position'] = slim_elements_df['position'].astype('category')
    slim_elements_df['team_name'] = slim_elements_df['team_name'].astype('category')
    
    slim_elements_df.drop(['first_name','second_name', 'element_type', 'team', 'value_season', 'now_cost'], axis=1, inplace=True)
    
    # Load history
    all_history_df = load_history(elements_df)
    all_history_df['player'] = (all_history_df.element.map(elements_df.set_index('id').first_name) + 
                                 " " + all_history_df.element.map(elements_df.set_index('id').second_name))
    
    return slim_elements_df, all_history_df, elements_df


def filter_data(slim_elements_df, all_history_df, 
                selected_teams=None, selected_position='All', min_week=0):
    """
    Filter player and history data based on selections.
    Optimized for memory and speed with category dtypes.
    
    Returns:
        tuple: (subset_df, fh_key_players_df, dynamic_table)
    """
    # Apply position and team filters to get subset of players
    subset_df = slim_elements_df.copy()
    if selected_position != 'All':
        subset_df = subset_df[subset_df['position'] == selected_position]
    if selected_teams:
        subset_df = subset_df[subset_df['team_name'].isin(selected_teams)]
    
    subset_ids = subset_df['id'].values
    
    # Filter history for selected players and weeks
    fh_key_players_df = all_history_df[
        (all_history_df['element'].isin(subset_ids)) &
        (all_history_df['round'] >= min_week)
    ].copy()
    
    # Add cumulative points and computed value
    fh_key_players_df['total_points_sum'] = fh_key_players_df.groupby('element')['total_points'].cumsum()
    
    # Join with player metadata (only needed columns, 'player' already exists from all_history_df)
    player_metadata = slim_elements_df[['id', 'price', 'team_name', 'position']].copy()
    fh_key_players_df = fh_key_players_df.merge(
        player_metadata,
        left_on='element', right_on='id', how='left'
    )
    fh_key_players_df['total_value'] = fh_key_players_df['total_points_sum'] / fh_key_players_df['price']
    
    # Create aggregated table for summary stats
    dynamic_table = fh_key_players_df.groupby(['player', 'team_name', 'position', 'price'], observed=True).agg({
        'total_points': 'sum',
        'defensive_contribution': 'sum',
        'bonus': 'sum'
    }).reset_index()
    dynamic_table['total_value'] = (dynamic_table['total_points'] / dynamic_table['price']).round(2)
    dynamic_table = dynamic_table.sort_values('total_points', ascending=False)
    
    return subset_df, fh_key_players_df, dynamic_table
