import streamlit as st
import pandas as pd
import io

# === PAGE CONFIGURATION ===
st.set_page_config(page_title="Vendor Analyst Generator", layout="wide")
st.title("📊 Vendor Analyst Generator")

# === SESSION STATE INITIALIZATION ===
if 'final_df' not in st.session_state:
    st.session_state.final_df = None

# === UTILITY FUNCTION ===
@st.cache_data
def to_excel(df):
    output = io.BytesIO()
    df.to_excel(output, index=False, sheet_name='Vendor Analyst', engine='openpyxl')
    return output.getvalue()

# === FILE UPLOADS ===
metabase_file = st.file_uploader("Upload Metabase CSV", type=["csv"])
spx_file = st.file_uploader("Upload SPX Excel File", type=["xlsx"])

# === MAIN LOGIC ===
if metabase_file and spx_file:
    if st.button("🚀 Generate Vendor Analyst"):
        try:
            # === LOAD FILES ===
            metabase = pd.read_csv(metabase_file)
            raw_spx = pd.read_excel(spx_file, sheet_name='RAW SPX WEEKLY LEADTIME', header=1, usecols="A:BK")
            data_dedicated = pd.read_excel(spx_file, sheet_name='DATA Dedicated', header=3)
            raw_spx_manual = pd.read_excel(
                spx_file,
                sheet_name='RAW SPX WEEKLY LEADTIME',
                header=1,
                usecols=["LT Number", "Data Nopol", "VENDOR MANUAL / NOT FOUND"]
            )
        except Exception as e:
            st.error(f"❌ Error reading files: {e}")
            st.session_state.final_df = None
            st.stop()

        try:
            # === CLEAN COLUMN NAMES ===
            for df in [metabase, raw_spx, data_dedicated, raw_spx_manual]:
                df.columns = df.columns.str.strip()

            # === MERGE FOR VENDOR BY LT NUMBER ===
            merged_df_lt = pd.merge(
                raw_spx,
                data_dedicated,
                left_on='Origin + Destination',
                right_on='uniq',
                how='left'
            )
            raw_spx['vendor_by_LTNumber'] = merged_df_lt['Vendor_y']

            # === CLEAN LICENSE PLATES ===
            metabase['Cleaned Nopol'] = metabase['trip_transporter_vehicle_license_plate'].astype(str).str.replace(" ", "").str.lower()
            raw_spx['Cleaned Data Nopol'] = raw_spx['Data Nopol'].astype(str).str.replace(" ", "").str.lower()

            # === MERGE FOR VENDOR BY NOPOL ===
            result_df = raw_spx.merge(
                metabase[['Cleaned Nopol', 'trip_transporter_name']],
                left_on='Cleaned Data Nopol',
                right_on='Cleaned Nopol',
                how='left'
            ).rename(columns={'trip_transporter_name': 'Vendor by Nopol'})

            result_df['Vendor by Nopol'] = result_df['Vendor by Nopol'].fillna('').str.strip()
            result_df['vendor_by_LTNumber'] = result_df['vendor_by_LTNumber'].fillna('').str.strip()
            result_df.drop(columns=['Cleaned Data Nopol', 'Cleaned Nopol'], inplace=True)

            # === INITIAL VENDOR ANALYST (BEFORE MANUAL) ===
            result_df['Vendor_Analyst_Pre_Manual'] = result_df['vendor_by_LTNumber']
            result_df.loc[result_df['Vendor_Analyst_Pre_Manual'] == '', 'Vendor_Analyst_Pre_Manual'] = result_df['Vendor by Nopol']

            # === MERGE MANUAL OVERRIDE ===
            if {'LT Number', 'Data Nopol'}.issubset(result_df.columns) and {'LT Number', 'Data Nopol'}.issubset(raw_spx_manual.columns):
                result_df = pd.merge(
                    result_df,
                    raw_spx_manual[['LT Number', 'Data Nopol', 'VENDOR MANUAL / NOT FOUND']],
                    on=['LT Number', 'Data Nopol'],
                    how='left'
                )
            else:
                st.warning("⚠️ Missing 'LT Number' or 'Data Nopol' columns for manual override merge.")
                result_df['VENDOR MANUAL / NOT FOUND'] = ''

            result_df.rename(columns={'VENDOR MANUAL / NOT FOUND': 'Vendor Manual'}, inplace=True)
            result_df['Vendor Manual'] = result_df['Vendor Manual'].fillna('').str.strip()

            # === FINAL VENDOR ANALYST LOGIC ===
            result_df['Vendor Analyst'] = result_df['Vendor_Analyst_Pre_Manual']
            result_df.loc[result_df['Vendor Analyst'] == '', 'Vendor Analyst'] = result_df['Vendor Manual']

            # Mark mismatches as [CHECK]
            mismatch = (
                (result_df['Vendor Manual'] != '') &
                (result_df['Vendor_Analyst_Pre_Manual'] != '') &
                (result_df['Vendor_Analyst_Pre_Manual'] != result_df['Vendor Manual'])
            )
            result_df.loc[mismatch, 'Vendor Analyst'] = "[CHECK] " # + result_df['Vendor Analyst']

            result_df.drop(columns=['Vendor_Analyst_Pre_Manual'], inplace=True)

            # === REORDER COLUMNS ===
            vendor_cols = ['vendor_by_LTNumber', 'Vendor by Nopol', 'Vendor Manual', 'Vendor Analyst']
            ordered_cols = [col for col in result_df.columns if col not in vendor_cols] + vendor_cols
            result_df = result_df[ordered_cols]

            # === SAVE RESULT ===
            st.session_state.final_df = result_df
            st.success("✅ Vendor Analyst generated successfully!")

        except Exception as e:
            st.error(f"❌ Error during processing: {e}")
            st.session_state.final_df = None

# === DISPLAY & DOWNLOAD RESULT ===
if st.session_state.final_df is not None:
    st.subheader("📋 Vendor Analyst Preview")
    st.dataframe(st.session_state.final_df.head(100), use_container_width=True)

    # === DOWNLOAD BUTTON (CSV) ===
    # Convert the dataframe to CSV bytes
    csv = st.session_state.final_df.to_csv(index=False).encode('utf-8')

    st.download_button(
        "📥 Download Full Result CSV",
        data=csv,
        file_name='vendor_analyst_result.csv',
        mime='text/csv'
    )

elif not metabase_file or not spx_file:
    st.info("📁 Please upload both Metabase and SPX Excel files to continue.")
