"""Read-only validation of the standalone Compose stacks (requires Docker Compose)."""
import json
from pathlib import Path
import subprocess
import unittest


class ProductionComposeTests(unittest.TestCase):
    def test_local_stack_is_standalone_and_preserves_data_locations(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run([
            'docker', 'compose', '--env-file', '.env.example',
            '-f', 'docker-compose.bot-local.yml', 'config', '--no-env-resolution', '--format', 'json',
        ], cwd=root, check=True, capture_output=True, text=True)
        config = json.loads(result.stdout)
        self.assertEqual(config['name'], 'hikari-miniapp-dev')
        services = config['services']
        self.assertEqual(set(services), {'database', 'migrate', 'backend', 'gateway', 'miniapp', 'bot'})
        self.assertEqual(services['backend']['depends_on']['migrate']['condition'], 'service_completed_successfully')
        self.assertEqual(services['backend']['environment']['DATABASE_URL'], services['migrate']['environment']['DATABASE_URL'])
        self.assertIn('/hikari_bot_local_20261117?', services['backend']['environment']['DATABASE_URL'])
        self.assertEqual(config['volumes']['postgres_data']['name'], 'hikari-miniapp-dev_postgres_data')
        self.assertEqual({int(p['published']) for p in services['miniapp']['ports']}, {5173})
        self.assertEqual(sorted(p.name for p in root.glob('*compose*.yml')), ['docker-compose.bot-local.yml', 'docker-compose.production.yml'])

    def test_nginx_template_keeps_runtime_variables_and_requires_certificate(self):
        root = Path(__file__).resolve().parents[1]
        template = root / 'deploy' / 'nginx.production.conf.template'
        script = """
envsubst '${MINIAPP_DOMAIN} ${MINIAPP_HTTPS_PORT}' < /template > /etc/nginx/conf.d/default.conf
cat /etc/nginx/conf.d/default.conf
nginx -t
"""
        result = subprocess.run([
            'docker', 'run', '--rm', '--entrypoint', 'sh',
            '--add-host', 'backend:127.0.0.1',
            '-e', 'MINIAPP_DOMAIN=hikari.jpegmushrum.ru', '-e', 'MINIAPP_HTTPS_PORT=8443',
            '--mount', f'type=bind,source={template},target=/template,readonly',
            'nginx:1.28-alpine', '-ec', script,
        ], check=False, capture_output=True, text=True)
        self.assertIn('https://hikari.jpegmushrum.ru:8443$request_uri', result.stdout)
        self.assertIn('try_files $uri', result.stdout)
        self.assertNotIn('${MINIAPP_', result.stdout)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('cannot load certificate', result.stderr)
        self.assertIn('/etc/hikari/tls/fullchain.pem', result.stderr)

    def test_production_contract(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run([
            'docker', 'compose', '--env-file', '.env.example',
            '-f', 'docker-compose.production.yml',
            'config', '--no-env-resolution', '--format', 'json',
        ], cwd=root, check=True, capture_output=True, text=True)
        services = json.loads(result.stdout)['services']
        self.assertNotIn('gateway', services)
        for service in ['database', 'backend', 'bot']:
            self.assertFalse(services[service].get('ports'))
        web = services['miniapp']
        self.assertEqual({int(p['published']) for p in web['ports']}, {880, 8443})
        self.assertEqual(services['bot']['environment']['MINIAPP_URL'], 'https://hikari.jpegmushrum.ru:8443')
        source = next(v for v in services['backend-import']['volumes'] if v['target']=='/legacy')
        self.assertEqual(source['source'], 'legacy_snapshot')
        self.assertTrue(source['read_only'])
        for dependency in ['legacy-snapshot', 'backend-migrate']:
            self.assertEqual(services['backend-import']['depends_on'][dependency]['condition'], 'service_completed_successfully')
        self.assertEqual(services['backend']['depends_on']['backend-import']['condition'], 'service_completed_successfully')
        self.assertEqual(services['bot']['depends_on']['backend-import']['condition'], 'service_completed_successfully')
