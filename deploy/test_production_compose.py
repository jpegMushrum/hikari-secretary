"""Read-only validation of the standalone Compose stacks (requires Docker Compose)."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class ProductionComposeTests(unittest.TestCase):
    def compose_config(self, filename, *options, settings=None):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / '.env').write_text('BOT_ENV_TEST_MARKER=from-root-file\n')
            (project / 'backend').mkdir()
            (project / 'backend' / '.env').write_text('')
            result = subprocess.run([
                'docker', 'compose', '--project-directory', str(project),
                '--env-file', str(root / '.env.example'), '-f', str(root / filename),
                *options, 'config', '--format', 'json',
            ], cwd=project, env={**os.environ, **(settings or {})}, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)

    def test_local_ai_uses_configured_provider_target_and_schedule(self):
        settings = {
            'DEEPSEEK_API_KEY': 'local-test-key',
            'DEEPSEEK_MODEL': 'local-test-model',
            'AI_TOPIC_TARGET_KEY': 'local-test-target',
            'AI_TOPIC_AUTO_PUBLISH_TIME': '19:45',
            'TIMEZONE': 'UTC',
        }
        services = self.compose_config('docker-compose.bot-local.yml', settings=settings)['services']
        for name, value in settings.items():
            self.assertEqual(services['backend']['environment'].get(name), value)
        self.assertEqual(services['bot']['environment']['BOT_ENV_TEST_MARKER'], 'from-root-file')
        for name in ('AI_TOPIC_TARGET_KEY', 'AI_TOPIC_AUTO_PUBLISH_TIME'):
            self.assertNotIn(name, services['bot']['environment'])

    def test_local_stack_is_standalone_and_preserves_data_locations(self):
        root = Path(__file__).resolve().parents[1]
        config = self.compose_config('docker-compose.bot-local.yml')
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

    def production_services(self, *profile_options, settings=None):
        return self.compose_config('docker-compose.production.yml', *profile_options, settings=settings)['services']

    def test_production_uses_the_release_images_for_all_application_services(self):
        refs = {name: f"ghcr.io/example/hikari-secretary-{name}@sha256:{'a' * 64}"
                for name in ('backend', 'bot', 'miniapp')}
        services = self.production_services(settings={f'{k.upper()}_IMAGE': v for k, v in refs.items()})
        for name, ref in refs.items():
            self.assertEqual(services[name]['image'], ref)
        self.assertEqual(services['backend-migrate']['image'], refs['backend'])

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

    def test_journal_tags_are_scoped_to_the_production_project(self):
        for project in ('hikari-secretary', 'isolated-restore'):
            config = self.compose_config('docker-compose.production.yml', '--profile', 'legacy-import',
                                         settings={'COMPOSE_PROJECT_NAME': project, 'HIKARI_LOG_DRIVER': 'journald'})
            for name, service in config['services'].items():
                self.assertEqual(service['logging'], {'driver': 'journald', 'options': {'tag': f'{project}/{name}'}})

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
        self.assertEqual(Path(importer['build']['context']).name, 'backend')
        dockerfile = Path(__file__).resolve().parents[1] / 'backend' / importer['build']['dockerfile']
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
