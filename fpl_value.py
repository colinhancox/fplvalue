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
slim_elements_df['position'] = slim_elements_df.element_type.map(elements_types_df.set_index('id').singular_name)
slim_elements_df['team_name'] = slim_elements_df.team.map(teams_df.set_index('id').name)
slim_elements_df['value'] = slim_elements_df.value_season.astype(float)
slim_elements_df['price'] = slim_elements_df.now_cost / 10
slim_elements_df['selected_by_percent'] = slim_elements_df.selected_by_percent.astype(float)
slim_elements_df['player'] = slim_elements_df.first_name + " " + slim_elements_df.second_name
slim_elements_df.drop(['first_name','second_name'], axis=1, inplace=True)

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
all_history_df['player'] = all_history_df.element.map(elements_df.set_index('id').first_name) + " " + all_history_df.element.map(elements_df.set_index('id').second_name)

# Sidebar filters
st.sidebar.title('Selections')
select_team = st.sidebar.multiselect("Teams", slim_elements_df['team_name'].unique().tolist())
select_position = st.sidebar.radio("Position", ('All','Goalkeeper','Defender', 'Midfielder', 'Forward'))
add_slider = st.sidebar.slider("Start from week", 0, int(all_history_df['round'].max()))
select_colour = st.sidebar.radio("Colour by", ('position', 'team_name'))

# Filter slim_elements_df
subset_df = slim_elements_df.copy()
if select_team:
    subset_df = subset_df[subset_df['team_name'].isin(select_team)]
if select_position != 'All':
    subset_df = subset_df[subset_df['position'] == select_position]

# Filter history based on subset_df and week
fh_key_players_df = all_history_df[
    (all_history_df['element'].isin(subset_df['id'])) &
    (all_history_df['round'] >= add_slider)
].copy()

fh_key_players_df['total_points_sum'] = fh_key_players_df.groupby('player')['total_points'].cumsum()
fh_key_players_df = fh_key_players_df.merge(
    slim_elements_df[['id', 'price', 'team_name', 'position']],
    left_on='element', right_on='id', how='left'
)
fh_key_players_df['total_value'] = fh_key_players_df['total_points_sum'] / fh_key_players_df['price']

# Create dynamic_table
dynamic_table = fh_key_players_df.groupby(['player', 'team_name', 'position', 'price']).agg({
    'total_points': 'sum'
}).reset_index()
dynamic_table['total_value'] = (dynamic_table['total_points'] / dynamic_table['price']).round(2)
dynamic_table = dynamic_table.sort_values('total_points', ascending=False)

# Filter dynamic_table by team/position again (optional)
if select_team:
    dynamic_table = dynamic_table[dynamic_table['team_name'].isin(select_team)]
if select_position != 'All':
    dynamic_table = dynamic_table[dynamic_table['position'] == select_position]

# Use dynamic_table for player dropdown
sorted_players = dynamic_table['player'].unique().tolist()
select_player = st.sidebar.multiselect("Players", sorted_players)

# If no player selected, use all
if not select_player:
    select_player = sorted_players

# Final filter on fh_key_players_df
fh_key_players_df = fh_key_players_df[fh_key_players_df['player'].isin(select_player)]

# Update subset_df based on selected players
subset_df = subset_df[subset_df['player'].isin(select_player)]

# Charts and tables
st.title('FPL Value Analysis')
st.text('Value = Points/Price for the selected time period.')

x_axis = st.sidebar.selectbox("X Axis", ('price', 'total_points', 'total_value'))
y_axis = st.sidebar.selectbox("Y Axis", ('total_points', 'total_value', 'price'))
size_axis = st.sidebar.selectbox("Size", ('total_value', 'total_points', 'price'))

st.subheader("Player Comparison")
st.write("Select the X axis, Y axis and Size in the sidebar.")
scatter_chart3 = st.altair_chart(
    alt.Chart(dynamic_table).mark_circle(size=160).encode(
        x=alt.X(x_axis, scale=alt.Scale(zero=False)),
        y=y_axis,
        color=select_colour,
        size=size_axis,
        tooltip=['player', 'price', 'total_points', 'total_value']
    ).interactive().properties(width=1000, height=400)
)

st.subheader("Player details")
st.write("Click on a column to sort")
st.dataframe(data=dynamic_table, width=1000, height=300)

# Sort for trend charts
fh_key_players_df = fh_key_players_df.sort_values('total_points', ascending=False)

st.subheader("Player performance by week")
trend = st.altair_chart(
    alt.Chart(fh_key_players_df).mark_line(point=True).encode(
        x=alt.X('round', axis=alt.Axis(tickMinStep=1)),
        y=alt.Y('total_points'),
        color=alt.Color('player:N', sort=sorted_players),
        tooltip=['player', 'total_points']
    ).interactive().properties(width=1000, height=400)
)

st.subheader("Accummulated player performance")
form_trend = st.altair_chart(
    alt.Chart(fh_key_players_df).mark_line(point=True).encode(
        x=alt.X('round', axis=alt.Axis(tickMinStep=1)),
        y=alt.Y('total_points_sum'),
        color=alt.Color('player:N', sort=sorted_players),
        tooltip=['player', 'total_points_sum']
    ).interactive().properties(width=1000, height=400)
)
