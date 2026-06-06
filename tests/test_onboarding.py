"""Onboarding: non-secrets to config, secrets to the store, never leaked."""

from citevahti.credentials import NCBI_API_KEY, ZOTERO_WRITE_KEY, InMemoryCredentialStore
from citevahti.onboarding import OnboardingService
from citevahti.state import CiteVahtiStore

SECRET = "ZZZ-super-secret-write-key-123"


class OkValidators:
    def validate_zotero_key(self, key, user_id):
        return True, "ok", user_id

    def validate_ncbi_key(self, key, email):
        return True, "ok"


class FailZoteroValidator:
    def validate_zotero_key(self, key, user_id):
        return False, "key has no write access", None

    def validate_ncbi_key(self, key, email):
        return True, "ok"


def svc(tmp_path, validators=None, cred=None):
    store = CiteVahtiStore(tmp_path)
    store.init()
    return OnboardingService(store, credential_store=cred or InMemoryCredentialStore(),
                             validators=validators), store


def test_non_secrets_written_to_config(tmp_path):
    s, store = svc(tmp_path, validators=OkValidators())
    s.onboard(ncbi_email="researcher@example.org", zotero_user_id="123456",
              default_collection_key="T7XK7MJH", zotero_write_key=SECRET)
    cfg = store.load_config()
    assert cfg.pubmed.contact_email == "researcher@example.org"
    assert cfg.zotero.user_id == "123456" and cfg.zotero.library_id == "123456"
    assert cfg.zotero.default_collection_key == "T7XK7MJH"
    assert cfg.writeback.web_api_user_id == "123456"


def test_secret_stored_in_store_not_config(tmp_path):
    cred = InMemoryCredentialStore()
    s, store = svc(tmp_path, validators=OkValidators(), cred=cred)
    rep = s.onboard(zotero_user_id="123456", zotero_write_key=SECRET)
    assert cred.get_secret(ZOTERO_WRITE_KEY) == SECRET          # in the secret store
    assert rep.secrets_stored == [ZOTERO_WRITE_KEY]             # names only
    # the secret value must NOT appear anywhere in the config file
    assert SECRET not in store.config_path.read_text()
    # nor in the (serialized) report
    assert SECRET not in rep.model_dump_json()


def test_writeback_enabled_on_zotero_key(tmp_path):
    s, store = svc(tmp_path, validators=OkValidators())
    s.onboard(zotero_user_id="123456", zotero_write_key=SECRET)
    cfg = store.load_config()
    assert cfg.writeback.enabled is True and cfg.writeback.kind == "web_api"


def test_validation_failure_blocks_storage(tmp_path):
    cred = InMemoryCredentialStore()
    s, store = svc(tmp_path, validators=FailZoteroValidator(), cred=cred)
    rep = s.onboard(zotero_user_id="123456", zotero_write_key=SECRET)
    assert cred.get_secret(ZOTERO_WRITE_KEY) is None            # not stored
    assert ZOTERO_WRITE_KEY in rep.secrets_skipped
    assert rep.validations[ZOTERO_WRITE_KEY].startswith("failed")
    # writeback not enabled when the key wasn't stored
    assert store.load_config().writeback.enabled is False


def test_ncbi_key_optional(tmp_path):
    cred = InMemoryCredentialStore()
    s, _ = svc(tmp_path, validators=OkValidators(), cred=cred)
    rep = s.onboard(ncbi_email="x@y.org", ncbi_api_key="ncbi-secret-key")
    assert cred.get_secret(NCBI_API_KEY) == "ncbi-secret-key"
    assert NCBI_API_KEY in rep.secrets_stored


def test_env_backend_does_not_store_secret(tmp_path):
    cred = InMemoryCredentialStore()
    s, store = svc(tmp_path, validators=OkValidators(), cred=cred)
    rep = s.onboard(zotero_user_id="123456", zotero_write_key=SECRET, secrets_backend="env")
    assert cred.get_secret(ZOTERO_WRITE_KEY) is None            # env backend persists nothing
    assert rep.secrets_stored == []
    assert "env-injected" in rep.validations[ZOTERO_WRITE_KEY]
    assert SECRET not in store.config_path.read_text()


def test_audit_records_config_save(tmp_path):
    s, store = svc(tmp_path, validators=OkValidators())
    s.onboard(zotero_user_id="123456", zotero_write_key=SECRET)
    assert "config.save" in [e.event for e in store.audit.entries()]
    assert store.audit.verify() is True
