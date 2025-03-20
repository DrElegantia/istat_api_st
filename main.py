import streamlit as st
from istatapi import discovery, retrieval
import plotly.express as px
import pandas as pd

st.title("Visualizzazione dati ISTAT con istatapi")

# 1. Recupera e mostra i dataset disponibili
available_datasets = discovery.all_available()
st.subheader("Dataset disponibili")
st.dataframe(available_datasets)  # Visualizza il DataFrame dei dataset

# Estrai la lista delle descrizioni
dataset_descriptions = available_datasets.df_description.tolist()

# Selezione del primo dataset
st.markdown("### Dataset 1")
selected_dataset_desc1 = st.selectbox("Seleziona il primo dataset", dataset_descriptions, key="ds1")
indice1 = dataset_descriptions.index(selected_dataset_desc1)
dataset_id1 = available_datasets.iloc[indice1]["df_id"]
st.write("ID del primo dataset:", dataset_id1)

# Selezione del secondo dataset
st.markdown("### Dataset 2")
selected_dataset_desc2 = st.selectbox("Seleziona il secondo dataset", dataset_descriptions, key="ds2")
indice2 = dataset_descriptions.index(selected_dataset_desc2)
dataset_id2 = available_datasets.iloc[indice2]["df_id"]
st.write("ID del secondo dataset:", dataset_id2)

# 2. Inizializza i due dataset
ds1 = discovery.DataSet(dataflow_identifier=dataset_id1)
ds2 = discovery.DataSet(dataflow_identifier=dataset_id2)

# Pulsanti per caricare i dataset (senza filtri)
col1, col2 = st.columns(2)
with col1:
    if st.button("Carica Dataset 1", key="load1"):
        data_full1 = retrieval.get_data(ds1)
        st.session_state["data_full1"] = data_full1
        st.success("Dataset 1 caricato con successo!")
        st.dataframe(data_full1)
with col2:
    if st.button("Carica Dataset 2", key="load2"):
        data_full2 = retrieval.get_data(ds2)
        st.session_state["data_full2"] = data_full2
        st.success("Dataset 2 caricato con successo!")
        st.dataframe(data_full2)


# Funzione per il filtraggio usando descrizioni se disponibili
def filtra_dataset(data, ds, key_prefix):
    colonne_escluse = ["TIME_PERIOD", "OBS_VALUE"]
    df_filtrato = data.copy()
    for col in data.columns:
        if col in colonne_escluse:
            continue
        try:
            mapping_df = ds.get_dimension_values(col)
            if isinstance(mapping_df, pd.DataFrame) and {"values_ids", "values_description"}.issubset(
                    mapping_df.columns):
                mapping = dict(zip(mapping_df["values_ids"], mapping_df["values_description"]))
                unique_ids = sorted(df_filtrato[col].dropna().unique())
                options = [(uid, mapping.get(uid, uid)) for uid in unique_ids]
                options.sort(key=lambda t: t[1])
                selected_tuple = st.selectbox(f"Filtra '{col}' per {key_prefix}", options, key=f"{key_prefix}_{col}",
                                              format_func=lambda x: x[1])
                selected_val = selected_tuple[0]
            else:
                unique_vals = sorted(df_filtrato[col].dropna().unique())
                selected_val = st.selectbox(f"Filtra '{col}' per {key_prefix}", unique_vals, key=f"{key_prefix}_{col}")
        except Exception:
            unique_vals = sorted(df_filtrato[col].dropna().unique())
            if len(unique_vals) > 1:
                selected_val = st.selectbox(f"Filtra '{col}' per {key_prefix}", unique_vals, key=f"{key_prefix}_{col}")
            else:
                continue
        df_filtrato = df_filtrato[df_filtrato[col] == selected_val]
    return df_filtrato


# Se entrambi i dataset sono stati caricati, applica il filtraggio
if "data_full1" in st.session_state and "data_full2" in st.session_state:
    st.markdown("### Filtra Dataset 1")
    data1 = st.session_state["data_full1"]
    data1_filtrato = filtra_dataset(data1, ds1, key_prefix="Dataset 1")
    st.dataframe(data1_filtrato)

    st.markdown("### Filtra Dataset 2")
    data2 = st.session_state["data_full2"]
    data2_filtrato = filtra_dataset(data2, ds2, key_prefix="Dataset 2")
    st.dataframe(data2_filtrato)

    # Aggiungi una colonna identificativa per ciascun dataset
    data1_filtrato["Dataset"] = selected_dataset_desc1
    data2_filtrato["Dataset"] = selected_dataset_desc2

    # Combina i due dataset
    combined_data = pd.concat([data1_filtrato, data2_filtrato], ignore_index=True)

    st.subheader("Grafico combinato dei due dataset")
    tutte_colonne = combined_data.columns.tolist()
    x_axis = st.selectbox("Seleziona la colonna per l'asse X", tutte_colonne, key="x_axis")

    colonne_numeriche = combined_data.select_dtypes(include=["number"]).columns.tolist()
    if not colonne_numeriche:
        st.warning("Nessuna colonna numerica trovata per l'asse Y.")
    else:
        y_axis = st.selectbox("Seleziona la colonna per l'asse Y", colonne_numeriche, key="y_axis")

        # Opzioni di trasformazione
        transform_type = st.radio("Seleziona il tipo di trasformazione",
                                  options=["Valori originali", "Variazione anno su anno", "Indicizzati a 100"])

        combined_data_transformed = combined_data.copy()

        # Converti TIME_PERIOD in datetime se presente
        if "TIME_PERIOD" in combined_data_transformed.columns:
            combined_data_transformed["TIME_PERIOD"] = pd.to_datetime(combined_data_transformed["TIME_PERIOD"])

        if transform_type == "Variazione anno su anno":
            combined_data_transformed = combined_data_transformed.sort_values(by=["Dataset", "TIME_PERIOD"])
            combined_data_transformed["y_transformed"] = combined_data_transformed.groupby("Dataset")[
                                                             y_axis].pct_change() * 100
            y_label = f"Variazione {y_axis} (%)"
        elif transform_type == "Indicizzati a 100":
            # Permetti all'utente di scegliere l'anno base
            if "TIME_PERIOD" in combined_data_transformed.columns:
                base_year = st.selectbox("Scegli l'anno base",
                                         sorted(combined_data_transformed["TIME_PERIOD"].dt.year.unique()))


                def index_series(group):
                    base_vals = group.loc[group["TIME_PERIOD"].dt.year == base_year, y_axis]
                    if not base_vals.empty:
                        base_val = base_vals.iloc[0]
                        return group[y_axis] / base_val * 100
                    else:
                        return group[y_axis]


                combined_data_transformed["y_transformed"] = combined_data_transformed.groupby("Dataset").apply(
                    index_series).reset_index(level=0, drop=True)
                y_label = f"{y_axis} indicizzato (base {base_year} = 100)"
            else:
                st.warning("La colonna 'TIME_PERIOD' non è disponibile per l'indicizzazione.")
                combined_data_transformed["y_transformed"] = combined_data_transformed[y_axis]
                y_label = y_axis
        else:
            combined_data_transformed["y_transformed"] = combined_data_transformed[y_axis]
            y_label = y_axis

        fig = px.line(combined_data_transformed, x=x_axis, y="y_transformed", color="Dataset",
                      title=f"Grafico combinato dei due dataset ({transform_type})",
                      labels={"y_transformed": y_label})
        st.plotly_chart(fig)
