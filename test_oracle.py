import getpass
import pyodbc

USERNAME = "HOSTEL_OWNER"
DSN = "SmartHostelOracle"
DRIVER = "Oracle in OraDB21Home1"

password = getpass.getpass("Enter Oracle password: ")

def protect(value):
    """Escape an ODBC connection-string value."""
    return "{" + value.replace("}", "}}") + "}"

credentials = (
    f"UID={USERNAME};"
    f"PWD={protect(password)};"
)

connections = {
    "DSN connection": (
        f"DSN={DSN};"
        + credentials
    ),
    "Direct XEPDB1 connection": (
        f"DRIVER={{{DRIVER}}};"
        "DBQ=//127.0.0.1:1521/XEPDB1;"
        + credentials
    ),
}

for name, connection_string in connections.items():
    print(f"\nTesting: {name}")

    try:
        with pyodbc.connect(
            connection_string,
            timeout=10
        ) as connection:

            cursor = connection.cursor()

            cursor.execute("""
                SELECT
                    USER,
                    SYS_CONTEXT('USERENV', 'CON_NAME'),
                    SYS_CONTEXT('USERENV', 'SERVICE_NAME')
                FROM dual
            """)

            user, pdb, service = cursor.fetchone()

            print("SUCCESS")
            print("User:", user)
            print("Container:", pdb)
            print("Service:", service)

            cursor.execute("""
                SELECT COUNT(*)
                FROM user_tables
                WHERE table_name IN (
                    'ROOM', 'STUDENT', 'CATEGORY',
                    'STAFF', 'COMPLAINT',
                    'COMPLAINT_PHOTO',
                    'COMPLAINT_ASSIGNMENT',
                    'COMPLAINT_STATUS',
                    'COMPLAINT_FEEDBACK'
                )
            """)

            print("Project tables:", cursor.fetchone()[0])

    except pyodbc.Error as error:
        print("FAILED")
        print(str(error).split("\x00")[0])

password = None