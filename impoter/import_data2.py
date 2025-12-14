"""
A simple script to import transaction data from an XTB XLSX file.
"""
from tools.actions import import_xtb_transactions

def main():
    """Main function to run the import process."""
    
    # --- IMPORTANT ---
    # Please ensure the file path below is correct before running the script.
    file_path = "C:/Users/ukasz/Downloads/account_51885378_pl_xlsx_2005-12-31_2025-11-27/account_ike_51936682_pl_xlsx_2005-12-31_2025-11-27.xlsx"
    
    print(f"Starting import from: {file_path}")
    
    result = import_xtb_transactions(file_path)
    
    if "error" in result:
        print(f"\n[ERROR] An error occurred during import:")
        print(result["error"])
    else:
        print(f"\n[SUCCESS] {result['message']}")

if __name__ == '__main__':
    main()
