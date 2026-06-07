from app.services.proxies import ProxyService
from app.storage.base import Base
from app.storage.models import ProxyEndpoint
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_infer_source_from_label():
    db = make_session()
    proxy = ProxyEndpoint(label="the_speedx_http_http_1_1_1_1_80", proxy_url="http://1.1.1.1:80")
    db.add(proxy)
    db.commit()

    source = ProxyService(db).infer_source(proxy)

    assert source == "the_speedx"


def test_cleanup_invalid_proxies_removes_failed_without_success():
    db = make_session()
    service = ProxyService(db)
    good = service.import_proxy("manual-good", "http://1.1.1.1:80")
    bad = service.import_proxy("manual-bad", "http://2.2.2.2:80")
    service.mark_success(good)
    service.mark_failure(bad)

    removed = service.cleanup_invalid_proxies()

    assert removed == 1
    labels = [item.label for item in service.list_proxies()]
    assert labels == ["manual-good"]
