import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Vendor Analyst Generator", layout="wide")
st.title("📊 Vendor Analyst Generator")

# Initialize session state for the dataframe if it doesn't exist
if 'final_df' not in st.session_state:
    st.session_state.final_df = None

# Function to convert DataFrame to CSV bytes with caching (optimized for cloud)
@st.cache_data
def to_csv_bytes(df):
    output = io.BytesIO()
    df.to_csv(output, index=False, encoding='utf-8-sig')
    output.seek(0)
    return output

# === FILE UPLOADS ===
metabase_file = st.file_uploader("Upload Metabase CSV", type=["csv"])
spx_file = st.file_uploader("Upload SPX Excel File", type=["xlsx"])

# Check if files are uploaded and the generate button is clicked
if metabase_file and spx_file:
    if st.button("🚀 Generate Vendor Analyst"):
        # === LOAD FILES ===
        try:
            metabase = pd.read_csv(metabase_file)
            raw_spx = pd.read_excel(spx_file, sheet_name='RAW SPX WEEKLY LEADTIME', header=1, usecols="A:BK")
            data_dedicated = pd.read_excel(spx_file, sheet_name='DATA Dedicated', header=3)
            raw_spx_manual = pd.read_excel(spx_file, sheet_name='RAW SPX WEEKLY LEADTIME', header=1, usecols=["LT Number", "Data Nopol", "VENDOR MANUAL / NOT FOUND"])
        except Exception as e:
            st.error(f"Error reading files: {e}")
            st.session_state.final_df = None
            st.stop()

        # === DATA PROCESSING ===
        try:
            # Clean column names early
            metabase.columns = metabase.columns.str.strip()
            raw_spx.columns = raw_spx.columns.str.strip()
            data_dedicated.columns = data_dedicated.columns.str.strip()
            raw_spx_manual.columns = raw_spx_manual.columns.str.strip()

            # Merge raw_spx and data_dedicated to get vendor_by_LTNumber
            merged_df_lt = pd.merge(
                raw_spx,
                data_dedicated,
                left_on='Origin + Destination',
                right_on='uniq',
                how='left'
            )
            raw_spx['vendor_by_LTNumber'] = merged_df_lt['Vendor_y']

            # Clean license plates
            metabase['Cleaned Nopol'] = metabase['trip_transporter_vehicle_license_plate'].astype(str).str.replace(" ", "").str.lower()
            raw_spx['Cleaned Data Nopol'] = raw_spx['Data Nopol'].astype(str).str.replace(" ", "").str.lower()

            # Merge raw_spx with metabase to get Vendor by Nopol
            result_df = raw_spx.merge(
                metabase[['Cleaned Nopol', 'trip_transporter_name']],
                left_on='Cleaned Data Nopol',
                right_on='Cleaned Nopol',
                how='left'
            )
            result_df = result_df.rename(columns={'trip_transporter_name': 'Vendor by Nopol'})

            # Fill missing values
            result_df['Vendor by Nopol'] = result_df['Vendor by Nopol'].fillna('').astype(str).str.strip()
            result_df['vendor_by_LTNumber'] = result_df['vendor_by_LTNumber'].fillna('').astype(str).str.strip()

            # Drop temporary cleaned columns
            result_df = result_df.drop(columns=['Cleaned Data Nopol', 'Cleaned Nopol'])

            # Create initial 'Vendor Analyst' column
            result_df['Vendor_Analyst_Pre_Manual'] = result_df['vendor_by_LTNumber']
            result_df.loc[result_df['Vendor_Analyst_Pre_Manual'] == '', 'Vendor_Analyst_Pre_Manual'] = result_df['Vendor by Nopol']

            # Merge manual vendor info
            if 'LT Number' in result_df.columns and 'Data Nopol' in result_df.columns and 'LT Number' in raw_spx_manual.columns and 'Data Nopol' in raw_spx_manual.columns:
                result_df = pd.merge(result_df, raw_spx_manual[['LT Number', 'Data Nopol', 'VENDOR MANUAL / NOT FOUND']], on=['LT Number', 'Data Nopol'], how='left')
            else:
                st.warning("Could not merge Vendor Manual data. 'LT Number' or 'Data Nopol' columns not found.")
                result_df['VENDOR MANUAL / NOT FOUND'] = ''

            result_df = result_df.rename(columns={'VENDOR MANUAL / NOT FOUND': 'Vendor Manual'})
            result_df['Vendor Manual'] = result_df['Vendor Manual'].fillna('').astype(str).str.strip()

            # Final Vendor Analyst logic
            result_df['Vendor Analyst'] = result_df['Vendor_Analyst_Pre_Manual']
            result_df.loc[result_df['Vendor Analyst'] == '', 'Vendor Analyst'] = result_df['Vendor Manual']

            check_condition = (
                (result_df['Vendor Manual'] != '') &
                (result_df['Vendor_Analyst_Pre_Manual'] != '') &
                (result_df['Vendor_Analyst_Pre_Manual'] != result_df['Vendor Manual'])
            )
            result_df.loc[check_condition, 'Vendor Analyst'] = "[CHECK] " + result_df['Vendor Analyst']

            result_df = result_df.drop(columns=['Vendor_Analyst_Pre_Manual'])

            # Reorder columns to show vendor info last
            cols = list(result_df.columns)
            target_cols = ['vendor_by_LTNumber', 'Vendor by Nopol', 'Vendor Manual', 'Vendor Analyst']
            for col in target_cols:
                if col in cols:
                    cols.remove(col)
            cols += target_cols
            result_df = result_df[cols]

            # Store final result
            st.session_state.final_df = result_df
            # Drop duplicate rows with exactly the same information
            st.session_state.final_df.drop_duplicates(inplace=True)

            st.success("✅ Vendor Analyst generated successfully!")

        except Exception as e:
            st.error(f"An error occurred during data processing: {e}")
            st.session_state.final_df = None

# === RESULT DISPLAY AND DOWNLOAD ===
if st.session_state.final_df is not None:
    st.subheader("📋 Vendor Analyst Preview")
    st.dataframe(st.session_state.final_df.head(100), use_container_width=True)

    if len(st.session_state.final_df) > 50000:
        st.warning("⚠️ Output is large. Download may take longer.")

    csv_bytes = to_csv_bytes(st.session_state.final_df)

    st.download_button(
        label="📥 Download Full Result CSV",
        data=csv_bytes,
        file_name="vendor_analyst_result.csv",
        mime="text/csv"
    )

elif not metabase_file or not spx_file:
    st.info("📁 Please upload both Metabase and SPX Excel files to continue.")
