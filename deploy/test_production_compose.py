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

    def production_services(self, *profile_options):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run([
            'docker', 'compose', '--env-file', '.env.example',
            '-f', 'docker-compose.production.yml', *profile_options,
            'config', '--no-env-resolution', '--format', 'json',
        ], cwd=root, check=True, capture_output=True, text=True)
        return json.loads(result.stdout)['services']

    def test_production_contract(self):
        services = self.production_services()
        self.assertEqual(set(services), {'database', 'backend-migrate', 'backend', 'bot', 'miniapp'})
        self.assertEqual(services['backend']['depends_on']['backend-migrate']['condition'], 'service_completed_successfully')
        self.assertEqual(services['bot']['depends_on']['backend']['condition'], 'service_healthy')
        for service in ['database', 'backend', 'bot']:
            self.assertFalse(services[service].get('ports'))
        web = services['miniapp']
        self.assertEqual({int(p['published']) for p in web['ports']}, {880, 8443})
        self.assertEqual(services['bot']['environment']['MINIAPP_URL'], 'https://hikari.jpegmushrum.ru:8443')

    def test_legacy_import_is_opt_in_and_defaults_to_dry_run(self):
        services = self.production_services('--profile', 'legacy-import')
        importer = services['backend-import']
        snapshot = services['legacy-snapshot']
        self.assertEqual(importer['profiles'], ['legacy-import'])
        self.assertEqual(snapshot['profiles'], ['legacy-import'])
        self.assertNotEqual(importer['image'], services['backend']['image'])
        self.assertEqual(importer['build']['dockerfile'], 'Dockerfile.import-legacy')
        self.assertEqual(importer['build']['context'], services['backend']['build']['context'])
        # The exec entrypoint lets a compose run override supply --apply explicitly.
        dockerfile = Path(importer['build']['context']) / importer['build']['dockerfile']
        entrypoint = next(line for line in dockerfile.read_text().splitlines() if line.startswith('ENTRYPOINT '))
        self.assertEqual(json.loads(entrypoint.removeprefix('ENTRYPOINT ')), ['/app/import-legacy'])
        self.assertIsNone(importer.get('entrypoint'))
        self.assertEqual(importer['command'], ['--sqlite', '/legacy/bot.sqlite3', '--json'])
        source = next(v for v in importer['volumes'] if v['target'] == '/legacy')
        self.assertEqual(source['source'], 'legacy_snapshot')
        self.assertTrue(source['read_only'])
        for dependency in ['legacy-snapshot', 'backend-migrate']:
            self.assertEqual(importer['depends_on'][dependency]['condition'], 'service_completed_successfully')
        self.assertEqual(importer['depends_on']['database']['condition'], 'service_healthy')
        sqlite_source = next(v for v in snapshot['volumes'] if v['target'] == '/source')
        self.assertTrue(sqlite_source['read_only'])
