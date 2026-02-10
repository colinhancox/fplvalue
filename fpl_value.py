import streamlit as st
import altair as alt
from fpl_functions import load_data, prepare_data, filter_data

# Page configuration
st.set_page_config(
    layout="wide",
    initial_sidebar_state="auto",
    page_title='FPL Value Analysis',
    page_icon=None,
)

# Initialize session state for persisting filters
if 'select_team' not in st.session_state:
    st.session_state.select_team = []
if 'select_position' not in st.session_state:
    st.session_state.select_position = 'All'
if 'add_slider' not in st.session_state:
    st.session_state.add_slider = 0
if 'select_colour' not in st.session_state:
    st.session_state.select_colour = 'position'
if 'select_player' not in st.session_state:
    st.session_state.select_player = []

# Load and prepare data (cached)
@st.cache_data
def get_data():
    api_data = load_data()
    slim_elements_df, all_history_df, elements_df = prepare_data(api_data)
    return slim_elements_df, all_history_df


slim_elements_df, all_history_df = get_data()

# Get unique values for filters
team_options = sorted(slim_elements_df['team_name'].unique().tolist())
position_options = ('All','Goalkeeper','Defender', 'Midfielder', 'Forward')
max_week = int(all_history_df['round'].max())

# Sidebar filters - use keys to auto-sync with session_state
st.sidebar.title('Selections')
st.session_state.select_team = st.sidebar.multiselect(
    "Teams", 
    team_options,
    default=st.session_state.select_team
)
st.session_state.select_position = st.sidebar.radio(
    "Position", 
    position_options,
    index=position_options.index(st.session_state.select_position)
)
st.session_state.add_slider = st.sidebar.slider(
    "Start from week", 
    0, 
    max_week,
    value=st.session_state.add_slider
)
st.session_state.select_colour = st.sidebar.radio(
    "Colour by", 
    ('position', 'team_name'),
    index=('position', 'team_name').index(st.session_state.select_colour)
)

# Filter data based on selections (cached with parameters)
@st.cache_data
def get_filtered_data(team_tuple, position, min_week):
    subset_df, fh_key_players_df, dynamic_table = filter_data(
        slim_elements_df,
        all_history_df,
        selected_teams=list(team_tuple) if team_tuple else None,
        selected_position=position,
        min_week=min_week
    )
    return subset_df, fh_key_players_df, dynamic_table


subset_df, fh_key_players_df, dynamic_table = get_filtered_data(
    tuple(st.session_state.select_team), st.session_state.select_position, st.session_state.add_slider
)

# Get all available players based on current filters
# Sort by total_points in descending order instead of alphabetically
available_players = (
    dynamic_table.drop_duplicates('player')
    .sort_values('total_points', ascending=False)
    ['player'].tolist()
)

# Keep selected players that are still valid based on current filters
# This ensures selections persist even when other filters change
valid_selected = [p for p in st.session_state.select_player if p in available_players]
st.session_state.select_player = valid_selected

# Player selection multiselect
st.session_state.select_player = st.sidebar.multiselect(
    "Players", 
    available_players,
    default=st.session_state.select_player
)

# Filter to selected players (use all if none selected)
if st.session_state.select_player:
    fh_key_players_df = fh_key_players_df[fh_key_players_df['player'].isin(st.session_state.select_player)]
    dynamic_table = dynamic_table[dynamic_table['player'].isin(st.session_state.select_player)]
    players_for_charts = st.session_state.select_player
else:
    players_for_charts = available_players

# Main title and description
st.title('FPL Value Analysis')
st.text('Value = Points/Price for the selected time period.')

# Chart configuration
x_axis = st.sidebar.selectbox("X Axis", ('price', 'total_points', 'total_value', 'defensive_contribution', 'bonus'))
y_axis = st.sidebar.selectbox("Y Axis", ('total_points', 'total_value', 'price', 'defensive_contribution', 'bonus'))
size_axis = st.sidebar.selectbox("Size", ('total_value', 'total_points', 'price', 'defensive_contribution', 'bonus'))

# Player Comparison Chart
st.subheader("Player Comparison")
st.write("Select the X axis, Y axis and Size in the sidebar.")
st.altair_chart(
    alt.Chart(dynamic_table).mark_circle(size=160).encode(
        x=alt.X(x_axis, scale=alt.Scale(zero=False)),
        y=y_axis,
        color=st.session_state.select_colour,
        size=size_axis,
        tooltip=['player', 'price', 'total_points', 'total_value']
    ).interactive().properties(width=1000, height=400)
)

# Player details table
st.subheader("Player details")
st.write("Click on a column to sort")
st.dataframe(data=dynamic_table, width=1000, height=300, use_container_width=True)

# Sort for trend charts
fh_key_players_df_sorted = fh_key_players_df.sort_values('round')

# Player performance by week
st.subheader("Player performance by week")
st.altair_chart(
    alt.Chart(fh_key_players_df_sorted).mark_line(point=True).encode(
        x=alt.X('round', axis=alt.Axis(tickMinStep=1)),
        y=alt.Y('total_points'),
        color=alt.Color('player:N', sort=players_for_charts),
        tooltip=['player', 'round', 'total_points']
    ).interactive().properties(width=1000, height=400)
)

# Accumulated player performance
st.subheader("Accumulated player performance")
st.altair_chart(
    alt.Chart(fh_key_players_df_sorted).mark_line(point=True).encode(
        x=alt.X('round', axis=alt.Axis(tickMinStep=1)),
        y=alt.Y('total_points_sum'),
        color=alt.Color('player:N', sort=players_for_charts),
        tooltip=['player', 'round', 'total_points_sum']
    ).interactive().properties(width=1000, height=400)
)

# Player defensive contribution by week
st.subheader("Player def con by week")
st.altair_chart(
    alt.Chart(fh_key_players_df_sorted).mark_line(point=True).encode(
        x=alt.X('round', axis=alt.Axis(tickMinStep=1)),
        y=alt.Y('defensive_contribution'),
        color=alt.Color('player:N', sort=players_for_charts),
        tooltip=['player', 'round', 'defensive_contribution']
    ).interactive().properties(width=1000, height=400)
)
