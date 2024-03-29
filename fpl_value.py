import requests
import pandas as pd
import numpy as np
import altair as alt
import streamlit as st
import webbrowser
import concurrent.futures

url = 'https://fantasy.premierleague.com/api/bootstrap-static/'

st.set_page_config(
    layout="wide",
    initial_sidebar_state="auto",
    page_title='FPL Value Analysis',
    page_icon=None,
)

@st.cache_data
def load_data():
    data = requests.get(url)
    return data

data = load_data()

json = data.json()

elements_df = pd.DataFrame(json['elements'])
elements_df = elements_df[elements_df.minutes > 0].reset_index()
elements_types_df = pd.DataFrame(json['element_types'])
teams_df = pd.DataFrame(json['teams'])

slim_elements_df = elements_df[['id', 'first_name','second_name','team','element_type','selected_by_percent','now_cost','minutes','transfers_in','value_season','total_points', 'points_per_game']].copy()
slim_elements_df.loc[:,('position')] = slim_elements_df.element_type.map(elements_types_df.set_index('id').singular_name)
slim_elements_df.loc[:,('team_name')] = slim_elements_df.team.map(teams_df.set_index('id').name)
slim_elements_df.loc[:,('value')] = slim_elements_df.value_season.astype(float)
slim_elements_df.loc[:,('price')] = slim_elements_df.now_cost/10
slim_elements_df.loc[:,('selected_by_percent')] = slim_elements_df.selected_by_percent.astype(float)
slim_elements_df.loc[:,('player')] = slim_elements_df.first_name + " " + slim_elements_df.second_name
slim_elements_df.drop([ 'first_name','second_name'], axis=1, inplace=True)

def load_player_history(element_id):
    url = f'https://fantasy.premierleague.com/api/element-summary/{element_id}/'
    r = requests.get(url)
    json = r.json()
    json_history_df = pd.DataFrame(json['history'])
    week_history_df = json_history_df[['element', 'round', 'total_points']]
    return week_history_df

@st.cache_data(ttl=86400)
def load_history():
    with st.spinner('Retrieving player history...'):
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = [executor.submit(load_player_history, element_id) for element_id in elements_df.id]
            all_history_df = pd.concat([future.result() for future in concurrent.futures.as_completed(futures)])
    return all_history_df

all_history_df = load_history()

subset_df = slim_elements_df

all_history_df.loc[:,('player')] = all_history_df.element.map(elements_df.set_index('id').first_name) + " " + all_history_df.element.map(elements_df.set_index('id').second_name)

players_list = all_history_df.groupby('player', sort=False)['player', 'total_points'].sum().reset_index()
players_list = players_list.sort_values(['total_points'], ascending=False)
players_list = players_list['player'].tolist()

st.title('FPL Value Analysis')
st.text('Value = Points/Price for the selected time period.')

st.sidebar.title('Selections')
select_team = st.sidebar.multiselect(
'Teams',
slim_elements_df.groupby('team_name').count().reset_index()['team_name'].tolist())
select_position = st.sidebar.radio("Position", ('All','Goalkeeper','Defender', 'Midfielder', 'Forward'))
select_colour = st.sidebar.radio("Colour by", ('position', 'team_name'))

if len(select_team) > 0:
    subset_df = slim_elements_df[slim_elements_df['team_name'].isin(select_team)]

if select_position != 'All':
    subset_df = subset_df[subset_df['position'] == select_position]    

select_player = st.sidebar.multiselect("Players", players_list)

last_round = int(all_history_df['round'].max())

add_slider = st.sidebar.slider(
    'Start from week',
    0, last_round
)

x_axis = st.sidebar.selectbox(
'X Axis',
('price', 'total_points', 'total_value'))

y_axis = st.sidebar.selectbox(
'Y Axis',
('total_points', 'total_value', 'price'))

size_axis = st.sidebar.selectbox(
'Size',
('total_value', 'total_points', 'price'))

# If no players are selected, select all players
if not select_player:
    select_player = players_list

key_players_df = all_history_df.query("player == @select_player").copy()

round_after = key_players_df['round'] >= add_slider

form_history_df = key_players_df[round_after]
fh_key_players_df = form_history_df.query("player == @select_player").copy()
fh_key_players_df.loc[:,('total_points_sum')]=fh_key_players_df.groupby(by=['player'])['total_points'].cumsum()

# Add total_value column
fh_key_players_df = fh_key_players_df.merge(slim_elements_df[['id', 'price', 'team_name', 'position']], left_on='element', right_on='id', how='left')
fh_key_players_df.loc[:,('total_value')] = fh_key_players_df['total_points_sum'] / fh_key_players_df['price']

# Update subset_df based on round_after selection
subset_df = subset_df[subset_df['id'].isin(fh_key_players_df['element'])]

# Aggregate fh_key_players_df by player and price
dynamic_table = fh_key_players_df.groupby(['player', 'team_name', 'position', 'price']).agg({'total_points': 'sum'}).reset_index()
dynamic_table.loc[:,('total_value')] = (dynamic_table['total_points'] / dynamic_table['price']).round(2)
dynamic_table = dynamic_table.sort_values('total_points',ascending=False)

if len(select_team) > 0:
    dynamic_table = dynamic_table[dynamic_table['team_name'].isin(select_team)]

if select_position != 'All':
   dynamic_table = dynamic_table[dynamic_table['position'] == select_position]    

st.subheader("Player details")
st.write("Click on a column to sort")
st.dataframe(data=dynamic_table, width=1000, height=300)

# Sort your DataFrame by 'total_points'
fh_key_players_df = fh_key_players_df.sort_values('total_points', ascending=False)

if len(select_team) > 0:
    fh_key_players_df = fh_key_players_df[fh_key_players_df['team_name'].isin(select_team)]

if select_position != 'All':
    fh_key_players_df = fh_key_players_df[fh_key_players_df['position'] == select_position]    

# List of players sorted by 'total_points'
sorted_players = dynamic_table['player'].unique()

st.subheader("Player performance by week")
trend = st.altair_chart(
    alt.Chart(fh_key_players_df).mark_line(point=True).encode(
    x=alt.X('round', axis=alt.Axis(tickMinStep=1)),
    y=alt.Y('total_points'),
    color=alt.Color('player:N', sort=list(sorted_players)),  # Specify the sorted list here
    tooltip=['player', 'total_points']
).interactive().properties(width=1000,height=400)
)

st.subheader("Accummulated player performance")
form_trend = st.altair_chart(
    alt.Chart(fh_key_players_df).mark_line(point=True).encode(
    x=alt.X('round', axis=alt.Axis(tickMinStep=1)),
    y=alt.Y('total_points_sum'),
    color=alt.Color('player:N', sort=list(sorted_players)),  # Specify the sorted list here
    tooltip=['player', 'total_points_sum']
).interactive().properties(width=1000,height=400)
)

st.subheader("Player Comparison")
st.write("Select the X axis, Y axis and Size in the sidebar.")
scatter_chart3 = st.altair_chart(
        alt.Chart(dynamic_table).mark_circle(size=160).encode(
            x=alt.X(x_axis,scale=alt.Scale(zero=False)),
            y=y_axis,
            color=select_colour,
            size=size_axis,
            tooltip=['player', 'price', 'total_points', 'total_value']
        ).interactive().properties(width=1000,height=400)
)
