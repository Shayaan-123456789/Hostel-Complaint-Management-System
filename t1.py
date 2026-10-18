import pyodbc
import getpass

password = getpass.getpass("Oracle password: ")

# Avoid malformed connection strings.
if any(ch in password for ch in ";{}"):
    print(
        "Password contains ODBC delimiter characters. "
        "Skipping the unquoted connection test."
    )
else:
    try:
        connection = pyodbc.connect(
            "DSN=SmartHostelOracle;"
            "UID=HOSTEL_OWNER;"
            f"PWD={password};",
            timeout=10
        )

        cursor = connection.cursor()

        cursor.execute("SELECT USER FROM dual")

        print("ODBC CONNECTION SUCCESSFUL")
        print("Connected as:", cursor.fetchone()[0])

        cursor.close()
        connection.close()

    except pyodbc.Error as error:
        print("ODBC CONNECTION FAILED")
        print(str(error).split("\x00")[0])