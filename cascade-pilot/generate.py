"""Generate a private, isolated two-host WireGuard transport pilot."""
import argparse
import ipaddress
import json
import os
import secrets
import subprocess
from pathlib import Path


def wg(command, data=None):
    return subprocess.run(['docker','run','--rm','-i','--entrypoint','wg',
                           '3wg-wireguard-runtime:local',command],input=data,
                          text=True,capture_output=True,check=True).stdout.strip()


def generate(output, exit_ip, engine='wireguard'):
    ipaddress.IPv4Address(exit_ip)
    if output.exists():
        raise ValueError('Output directory already exists; refusing to overwrite keys')
    os.umask(0o077)
    output.mkdir(parents=True, mode=0o700)
    private = {role:wg('genkey') for role in ('entry','exit')}
    public = {role:wg('pubkey',key+'\n') for role,key in private.items()}
    psk = wg('genpsk')
    masking = ''
    if engine == 'amneziawg':
        masking = 'Jc = 4\nJmin = 10\nJmax = 50\nS1 = 126\nS2 = 141\n'
        masking += ''.join(f'H{i+1} = {secrets.randbelow(400_000_000)+i*500_000_000+1000}\n' for i in range(4))
    for role in ('entry','exit'):
        target = output / role
        target.mkdir(mode=0o700)
        address = '10.254.203.1/30' if role=='entry' else '10.254.203.2/30'
        other = 'exit' if role=='entry' else 'entry'
        allowed = '0.0.0.0/0' if role=='entry' else '10.254.203.1/32, 10.203.0.0/24'
        endpoint = f'Endpoint = {exit_ip}:54443\nPersistentKeepalive = 25\n' if role=='entry' else ''
        config = (f'[Interface]\nPrivateKey = {private[role]}\nAddress = {address}\n'
                  f'ListenPort = 54443\nMTU = 1380\nTable = off\n{masking}\n[Peer]\n'
                  f'PublicKey = {public[other]}\nPresharedKey = {psk}\nAllowedIPs = {allowed}\n{endpoint}')
        (target/'wg-cascade.conf').write_text(config)
        service = dict(image='3wg-cascade-pilot:local',container_name='3wg-cascade-pilot-'+role,
                       restart='unless-stopped',cap_add=['NET_ADMIN'],read_only=True,
                       tmpfs=['/tmp','/run'],environment={'PILOT_ROLE':role,'PILOT_ENGINE':engine},
                       sysctls={'net.ipv4.ip_forward':'1','net.ipv4.conf.all.rp_filter':'0'},
                       volumes=['./wg-cascade.conf:/config/wg-cascade.conf:ro'])
        if role=='exit':service['ports']=['54443:54443/udp']
        if engine=='amneziawg':
            service['image']='3wg-cascade-pilot:amneziawg'
            service['devices']=['/dev/net/tun:/dev/net/tun']
        (target/'compose.json').write_text(json.dumps({'services':{'transport':service}},indent=2))
    print('Pilot configuration generated; keys were not printed. No client VPN entry is enabled.')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--exit-ip',required=True)
    parser.add_argument('--engine',choices=['wireguard','amneziawg'],default='wireguard')
    args=parser.parse_args()
    generate(args.output,args.exit_ip,args.engine)
