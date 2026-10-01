import paramiko

ip = "10.11.104.1"
password = "Tr1l@n133"
# Adicione os possiveis usuarios aqui, caso nao seja admin
usernames = ["admin", "trilan"]

def test_ssh(ip, username, password, **kwargs):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        print(f"[{username}] Testando com: {kwargs}")
        ssh.connect(ip, port=22, username=username, password=password, timeout=5, **kwargs)
        print(f"[{username}] SUCESSO!")
        ssh.close()
        return True
    except Exception as e:
        print(f"[{username}] FALHOU: {type(e).__name__} - {e}")
        return False

for user in usernames:
    print(f"\n--- Testando usuario: {user} ---")
    
    test_ssh(ip, user, password, allow_agent=False, look_for_keys=False)
    
    test_ssh(ip, user, password, allow_agent=False, look_for_keys=False, disabled_algorithms={'pubkeys': ['rsa-sha2-256', 'rsa-sha2-512']})

    test_ssh(ip, user + "+c", password, allow_agent=False, look_for_keys=False, disabled_algorithms={'pubkeys': ['rsa-sha2-256', 'rsa-sha2-512']})
