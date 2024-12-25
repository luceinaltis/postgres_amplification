import psycopg2
import subprocess
import time
import shutil
import os
from pathlib import Path

RUN_EVAL_DIR = Path(__file__).resolve().parent
BASE_DIR = RUN_EVAL_DIR.parent
SYSBENCH_DIR = BASE_DIR / 'sysbench'
SCRIPT_DIR = BASE_DIR / 'script'
CONFIG_DIR = BASE_DIR / 'config'
DATA_DIR = BASE_DIR / 'data'

class Database:
    def __init__(self):
        self.user = 'kihwan'
        self.database = 'postgres'
        self.port = 23456

    def set_user(self, user_name):
        self.user = user_name

    def set_datbase(self, database_name):
        self.database = database_name

    def query(self, query_string, autocommit=True):
        connection = psycopg2.connect(user=self.user, \
                                      dbname=self.database, \
                                      port=self.port)
        cursor = connection.cursor()
        connection.autocommit = autocommit
        result = None
        try:
            cursor.execute(query_string)
            result = cursor.fetchall()
        except Exception as e:
            print(f'Error: {e}')
        connection.close()
        return result

    def run_server(self):
        global SCRIPT_DIR

        print('Start DBMS')
        subprocess.run([f'{SCRIPT_DIR}/script_server/run_server.sh'], \
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        time.sleep(2)

    def shutdown_server(self):
        global SCRIPT_DIR

        print('Shutdown DBMS')
        subprocess.run([f'{SCRIPT_DIR}/script_server/shutdown_server.sh'], \
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        time.sleep(2)

    def install_server(self):
        global SCRIPT_DIR

        print('Install DBMS')
        subprocess.run([f'{SCRIPT_DIR}/script_server/install_server.sh'], \
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    def init_server(self):
        global SCRIPT_DIR, CONFIG_DIR, DATA_DIR

        print('Init DBMS')
        subprocess.run([f'{SCRIPT_DIR}/script_server/install_server.sh'], \
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        shutil.copy(f'{CONFIG_DIR}/postgresql.conf', '{DATA_DIR}/postgresql.conf')

class Evaluation:
    def __init__(self):
        self.db = Database()

    def create_sysbench_user(self):
        self.db.query("CREATE USER sbtest WITH PASSWORD 'sysbench'", autocommit=True)
        self.db.query("CREATE DATABASE sbtest", autocommit=True)
        self.db.query("GRANT ALL PRIVILEGES ON DATABASE sbtest TO sbtest", autocommit=True)
        self.db.query("ALTER DATABASE sbtest OWNER TO sbtest", autocommit=True)

    def prepare_data(self):
        global SYSBENCH_DIR
        subprocess.run([f'{SCRIPT_DIR}/sysbench.sh --prepare'], \
                        shell=True, check=True)

        print("vacuum start")
        self.db.query("VACUUM FULL", autocommit=True)

    def cleanup_data(self):
        global SYSBENCH_DIR
        subprocess.run([f'{SCRIPT_DIR}/sysbench.sh --cleanup'], \
                        shell=True, check=True)

    def run_sysbench(self):
        global SYSBENCH_DIR
        subprocess.run([f'{SCRIPT_DIR}/sysbench.sh --run &'], \
                        shell=True, check=True)

    def run_eval(self, compile_server=False, create_data=False):
        # Compile and init PostgreSQL server.
        if compile_server:
            self.db.install_server()
            self.db.init_server()

        # Prepare sysbench data used for evaluation.
        if create_data:
            self.db.run_server()

            self.create_sysbench_user()
            self.cleanup_data()
            self.prepare_data()

            self.db.shutdown_server()

        # Run sysbench evaluation.
        self.db.run_server()
        self.run_sysbench()

        # Warm up
        time.sleep(60)
        
        # Get line count of logfile
        with open(f'{BASE_DIR}/logfile', 'r') as f:
            line_count = len(f.readlines())

        time.sleep(60)

        # If output.dat exists, remove it.
        if Path(f'{BASE_DIR}/evaluation/output.dat').exists():
            os.remove(f'{BASE_DIR}/evaluation/output.dat')

        output_file = open(f'output.dat', 'a')
        output_file.write(f'#wamp\tramp\n')

        # Get subset data behind the line count.
        with open(f'{BASE_DIR}/logfile', 'r') as f:
            lines = f.readlines()[line_count:]

            for line in lines:
                if '[AMP]' in line:
                    split_words = line.split(' ')
                    wamp = split_words[2]
                    ramp = split_words[4]
                    page_type = split_words[5]

                    output_file.write(f'{wamp}\t{ramp}\t{page_type}')

        output_file.close()

        self.db.shutdown_server()
        

if __name__ == '__main__':
    evaluation = Evaluation()

    evaluation.run_eval(compile_server=False, create_data=True)
