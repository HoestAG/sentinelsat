import hashlib
import textwrap
from datetime import date, datetime, timedelta
from os import environ

import geojson
import py.path
import pytest
import requests_mock

from sentinelsat.sentinel import (InvalidChecksumError, SentinelAPI, SentinelAPIError, convert_timestamp, format_date,
                                  get_coordinates, md5_compare)


@pytest.mark.fast
def test_format_date():
    assert format_date(datetime(2015, 1, 1)) == '2015-01-01T00:00:00Z'
    assert format_date(date(2015, 1, 1)) == '2015-01-01T00:00:00Z'
    assert format_date('2015-01-01T00:00:00Z') == '2015-01-01T00:00:00Z'
    assert format_date('20150101') == '2015-01-01T00:00:00Z'
    assert format_date('NOW') == 'NOW'


@pytest.mark.fast
def test_convert_timestamp():
    assert convert_timestamp('/Date(1445588544652)/') == '2015-10-23T08:22:24Z'


@pytest.mark.fast
def test_md5_comparison():
    testfile_md5 = hashlib.md5()
    with open("tests/expected_search_footprints_s1.geojson", "rb") as testfile:
        testfile_md5.update(testfile.read())
        real_md5 = testfile_md5.hexdigest()
    assert md5_compare("tests/expected_search_footprints_s1.geojson", real_md5) is True
    assert md5_compare("tests/map.geojson", real_md5) is False


@pytest.mark.scihub
def test_SentinelAPI_connection():
    api = SentinelAPI(
        environ['SENTINEL_USER'],
        environ['SENTINEL_PASSWORD']
    )
    api.query('0 0,1 1,0 1,0 0', datetime(2015, 1, 1), datetime(2015, 1, 2))

    assert api.url == 'https://scihub.copernicus.eu/apihub/search?format=json&rows=15000'
    assert api.last_query == '(beginPosition:[2015-01-01T00:00:00Z TO 2015-01-02T00:00:00Z]) ' + \
                             'AND (footprint:"Intersects(POLYGON((0 0,1 1,0 1,0 0)))")'
    assert api.content.status_code == 200


@pytest.mark.scihub
def test_SentinelAPI_wrong_credentials():
    api = SentinelAPI(
        "wrong_user",
        "wrong_password"
    )
    with pytest.raises(SentinelAPIError) as excinfo:
        api.query('0 0,1 1,0 1,0 0', datetime(2015, 1, 1), datetime(2015, 1, 2))
    assert excinfo.value.http_status == 401

    with pytest.raises(SentinelAPIError):
        api.get_products_size()
        api.get_products()


@pytest.mark.fast
def test_api_query_format():
    api = SentinelAPI("mock_user", "mock_password")

    now = datetime.now()
    query = api.format_query('0 0,1 1,0 1,0 0', end_date=now)
    last_24h = format_date(now - timedelta(hours=24))
    assert api.url == 'https://scihub.copernicus.eu/apihub/search?format=json&rows=15000'
    assert query == '(beginPosition:[%s TO %s]) ' % (last_24h, format_date(now)) + \
                    'AND (footprint:"Intersects(POLYGON((0 0,1 1,0 1,0 0)))")'

    query = api.format_query('0 0,1 1,0 1,0 0', end_date=now, producttype='SLC')
    assert api.url == 'https://scihub.copernicus.eu/apihub/search?format=json&rows=15000'
    assert query == '(beginPosition:[%s TO %s]) ' % (last_24h, format_date(now)) + \
                    'AND (footprint:"Intersects(POLYGON((0 0,1 1,0 1,0 0)))") ' + \
                    'AND (producttype:SLC)'


@pytest.mark.scihub
def test_invalid_query():
    api = SentinelAPI(
        environ['SENTINEL_USER'],
        environ['SENTINEL_PASSWORD']
    )
    with pytest.raises(SentinelAPIError) as excinfo:
        api.query_raw("xxx:yyy")
    assert excinfo.value.msg is not None
    print(excinfo)


@pytest.mark.scihub
def test_set_base_url():
    api = SentinelAPI(
        environ['SENTINEL_USER'],
        environ['SENTINEL_PASSWORD'],
        'https://scihub.copernicus.eu/dhus/'
    )
    api.query('0 0,1 1,0 1,0 0', datetime(2015, 1, 1), datetime(2015, 1, 2))

    assert api.url == 'https://scihub.copernicus.eu/dhus/search?format=json&rows=15000'
    assert api.last_query == '(beginPosition:[2015-01-01T00:00:00Z TO 2015-01-02T00:00:00Z]) ' + \
                             'AND (footprint:"Intersects(POLYGON((0 0,1 1,0 1,0 0)))")'
    assert api.content.status_code == 200


@pytest.mark.fast
def test_trail_slash_base_url():
    base_urls = [
        'https://scihub.copernicus.eu/dhus/',
        'https://scihub.copernicus.eu/dhus'
    ]

    expected = 'https://scihub.copernicus.eu/dhus/'

    for test_url in base_urls:
        assert SentinelAPI._url_trail_slash(test_url) == expected
        api = SentinelAPI("mock_user", "mock_password",
            test_url
        )
        assert api.api_url == expected


@pytest.mark.fast
def test_get_coordinates():
    coords = ('-66.2695312 -8.0592296,-66.2695312 0.7031074,' +
              '-57.3046875 0.7031074,-57.3046875 -8.0592296,-66.2695312 -8.0592296')
    assert get_coordinates('tests/map.geojson') == coords


@pytest.mark.scihub
def test_get_product_info():
    api = SentinelAPI(
        environ['SENTINEL_USER'],
        environ['SENTINEL_PASSWORD']
    )

    expected_s1 = {
        'id': '8df46c9e-a20c-43db-a19a-4240c2ed3b8b',
        'size': 143549851,
        'md5': 'D5E4DF5C38C6E97BF7E7BD540AB21C05',
        'url': "https://scihub.copernicus.eu/apihub/odata/v1/Products('8df46c9e-a20c-43db-a19a-4240c2ed3b8b')/$value",
        'date': '2015-11-21T10:03:56Z',
        'footprint': '-5.880887 -63.852531,-5.075419 -67.495872,-3.084356 -67.066071,-3.880541 -63.430576,'
                     '-5.880887 -63.852531',
        'title': 'S1A_EW_GRDM_1SDV_20151121T100356_20151121T100429_008701_00C622_A0EC'
    }

    expected_s2 = {
        'date': '2015-12-27T14:22:29Z',
        'footprint': '-4.565257232533263 -58.80274769505742,-5.513960396525286 -58.80535376268811,-5.515947033626909 '
                     '-57.90315169909761,-5.516014389089381 -57.903151791669515,-5.516044812342758 -57.85874693129081,'
                     '-5.516142631941845 -57.814323596961835,-5.516075248310466 -57.81432351345917,-5.516633044843839 '
                     '-57.00018056571297,-5.516700066819259 -57.000180565731384,-5.51666329264377 -56.95603179187787,'
                     '-5.516693539799448 -56.91188395837315,-5.51662651925904 -56.91188396736038,-5.515947927683427 '
                     '-56.097209386295305,-5.516014937246069 -56.09720929423562,-5.5159111504805916 '
                     '-56.053056977999596,-5.515874390220655 -56.00892491028779,-5.515807411549814 -56.00892501130261,'
                     '-5.513685455771881 -55.10621586418906,-4.6092845892233 -55.108821882251775,-4.606372862374043 '
                     '-54.20840287327946,-3.658594390979672 -54.21169990975238,-2.710949551849636 -54.214267703869346,'
                     '-2.7127451087194463 -55.15704255065496,-2.71378646425769 -56.0563616875051,-2.7141556791285275 '
                     '-56.9561852630143,-2.713837142510183 -57.8999998009875,-3.6180222056692726 -57.90079161941062,'
                     '-3.616721351843382 -58.800616247288836,-4.565257232533263 -58.80274769505742',
        'id': '44517f66-9845-4792-a988-b5ae6e81fd3e',
        'md5': '48C5648C2644CE07207B3C943DEDEB44',
        'size': 5854429622,
        'title': 'S2A_OPER_PRD_MSIL1C_PDMC_20151228T112523_R110_V20151227T142229_20151227T142229',
        'url': "https://scihub.copernicus.eu/apihub/odata/v1/Products('44517f66-9845-4792-a988-b5ae6e81fd3e')/$value"
    }

    assert api.get_product_info('8df46c9e-a20c-43db-a19a-4240c2ed3b8b') == expected_s1
    assert api.get_product_info('44517f66-9845-4792-a988-b5ae6e81fd3e') == expected_s2


@pytest.mark.mock_api
def test_get_product_info_scihub_down():
    api = SentinelAPI("mock_user", "mock_password")

    with requests_mock.mock() as rqst:
        rqst.get(
            "https://scihub.copernicus.eu/apihub/odata/v1/Products('8df46c9e-a20c-43db-a19a-4240c2ed3b8b')/?$format=json",
            text="Mock SciHub is Down", status_code=503
        )
        with pytest.raises(SentinelAPIError) as excinfo:
            api.get_product_info('8df46c9e-a20c-43db-a19a-4240c2ed3b8b')

        rqst.get(
            "https://scihub.copernicus.eu/apihub/odata/v1/Products('8df46c9e-a20c-43db-a19a-4240c2ed3b8b')/?$format=json",
            text='{"error":{"code":null,"message":{"lang":"en","value":'
                 '"No Products found with key \'8df46c9e-a20c-43db-a19a-4240c2ed3b8b\' "}}}', status_code=500
        )
        with pytest.raises(SentinelAPIError) as excinfo:
            api.get_product_info('8df46c9e-a20c-43db-a19a-4240c2ed3b8b')
        assert excinfo.value.msg == "No Products found with key \'8df46c9e-a20c-43db-a19a-4240c2ed3b8b\' "

        rqst.get(
            "https://scihub.copernicus.eu/apihub/odata/v1/Products('8df46c9e-a20c-43db-a19a-4240c2ed3b8b')/?$format=json",
            text="Mock SciHub is Down", status_code=200
        )
        with pytest.raises(SentinelAPIError) as excinfo:
            api.get_product_info('8df46c9e-a20c-43db-a19a-4240c2ed3b8b')
        assert excinfo.value.msg == "Mock SciHub is Down"

        # Test with a real server response
        rqst.get(
            "https://scihub.copernicus.eu/apihub/odata/v1/Products('8df46c9e-a20c-43db-a19a-4240c2ed3b8b')/?$format=json",
            text=textwrap.dedent("""\
            <!doctype html>
            <title>The Sentinels Scientific Data Hub</title>
            <link href='https://fonts.googleapis.com/css?family=Open+Sans' rel='stylesheet' type='text/css'>
            <style>
            body { text-align: center; padding: 125px; background: #fff;}
            h1 { font-size: 50px; }
            body { font: 20px 'Open Sans',Helvetica, sans-serif; color: #333; }
            article { display: block; text-align: left; width: 820px; margin: 0 auto; }
            a { color: #0062a4; text-decoration: none; font-size: 26px }
            a:hover { color: #1b99da; text-decoration: none; }
            </style>

            <article>
            <img alt="" src="/datahub.png" style="float: left;margin: 20px;">
            <h1>The Sentinels Scientific Data Hub will be back soon!</h1>
            <div style="margin-left: 145px;">
            <p>
            Sorry for the inconvenience,<br/>
            we're performing some maintenance at the moment.<br/>
            </p>
            <!--<p><a href="https://scihub.copernicus.eu/news/News00098">https://scihub.copernicus.eu/news/News00098</a></p>-->
            <p>
            We'll be back online shortly!
            </p>
            </div>
            </article>
            """),
            status_code=502)
        with pytest.raises(SentinelAPIError) as excinfo:
            api.get_product_info('8df46c9e-a20c-43db-a19a-4240c2ed3b8b')
        print(excinfo.value)
        assert "The Sentinels Scientific Data Hub will be back soon!" in excinfo.value.msg


@pytest.mark.mock_api
def test_get_products_invalid_json():
    api = SentinelAPI("mock_user", "mock_password")
    with requests_mock.mock() as rqst:
        rqst.post(
            'https://scihub.copernicus.eu/apihub/search?format=json&rows=15000',
            text="{Invalid JSON response", status_code=200
        )
        with pytest.raises(SentinelAPIError) as excinfo:
            api.query(
                area=get_coordinates("tests/map.geojson"),
                initial_date="20151219",
                end_date="20151228",
                platformname="Sentinel-2"
            )
            api.get_products()
        assert excinfo.value.msg == "API response not valid. JSON decoding failed."


@pytest.mark.scihub
def test_footprints_s1():
    api = SentinelAPI(
        environ['SENTINEL_USER'],
        environ['SENTINEL_PASSWORD']
    )
    api.query(
        get_coordinates('tests/map.geojson'),
        datetime(2014, 10, 10), datetime(2014, 12, 31), producttype="GRD"
    )

    with open('tests/expected_search_footprints_s1.geojson', 'r') as geojson_file:
        expected_footprints = geojson.loads(geojson_file.read())
        # to compare unordered lists (JSON objects) they need to be sorted or changed to sets
        assert set(api.get_footprints()) == set(expected_footprints)


@pytest.mark.scihub
def test_footprints_s2():
    api = SentinelAPI(
        environ['SENTINEL_USER'],
        environ['SENTINEL_PASSWORD']
    )
    api.query(
        get_coordinates('tests/map.geojson'),
        "20151219", "20151228", platformname="Sentinel-2"
    )

    with open('tests/expected_search_footprints_s2.geojson', 'r') as geojson_file:
        expected_footprints = geojson.loads(geojson_file.read())
        # to compare unordered lists (JSON objects) they need to be sorted or changed to sets
        assert set(api.get_footprints()) == set(expected_footprints)


@pytest.mark.scihub
def test_s2_cloudcover():
    api = SentinelAPI(
        environ['SENTINEL_USER'],
        environ['SENTINEL_PASSWORD']
    )
    api.query(
        get_coordinates('tests/map.geojson'),
        "20151219", "20151228",
        platformname="Sentinel-2",
        cloudcoverpercentage="[0 TO 10]"
    )
    assert len(api.get_products()) == 3
    assert api.get_products()[0]["id"] == "6ed0b7de-3435-43df-98bf-ad63c8d077ef"
    assert api.get_products()[1]["id"] == "37ecee60-23d8-4ec2-a65f-2de24f51d30e"
    assert api.get_products()[2]["id"] == "0848f6b8-5730-4759-850e-fc9945d42296"


@pytest.mark.scihub
def test_get_products_size():
    api = SentinelAPI(
        environ['SENTINEL_USER'],
        environ['SENTINEL_PASSWORD']
    )
    api.query(
        get_coordinates('tests/map.geojson'),
        "20151219", "20151228", platformname="Sentinel-2"
    )
    assert api.get_products_size() == 63.58

    api.query_raw("S1A_WV_OCN__2SSH_20150603T092625_20150603T093332_006207_008194_521E")
    assert len(api.get_products()) > 0
    # Rounded to zero
    assert api.get_products_size() == 0


@pytest.mark.scihub
def test_download(tmpdir):
    api = SentinelAPI(
        environ['SENTINEL_USER'],
        environ['SENTINEL_PASSWORD']
    )
    uuid = "1f62a176-c980-41dc-b3a1-c735d660c910"
    filename = "S1A_WV_OCN__2SSH_20150603T092625_20150603T093332_006207_008194_521E"
    expected_path = tmpdir.join(filename + ".zip")

    # Download normally
    path, product_info = api.download(uuid, str(tmpdir), checksum=True)
    assert expected_path.samefile(path)
    assert product_info["id"] == uuid
    assert product_info["title"] == filename
    assert product_info["size"] == expected_path.size()

    hash = expected_path.computehash()
    modification_time = expected_path.mtime()
    expected_product_info = product_info

    # File exists, test with checksum
    # Expect no modification
    path, product_info = api.download(uuid, str(tmpdir), check_existing=True)
    assert expected_path.mtime() == modification_time
    assert product_info == expected_product_info

    # File exists, test without checksum
    # Expect no modification
    path, product_info = api.download(uuid, str(tmpdir), check_existing=False)
    assert expected_path.mtime() == modification_time
    assert product_info == expected_product_info

    # Create invalid file, expect re-download
    with expected_path.open("wb") as f:
        f.seek(expected_product_info["size"] - 1)
        f.write(b'\0')
    assert expected_path.computehash("md5") != hash
    path, product_info = api.download(uuid, str(tmpdir), check_existing=True)
    assert expected_path.computehash("md5") == hash
    assert product_info == expected_product_info

    # Test continue
    with expected_path.open("rb") as f:
        content = f.read()
    with expected_path.open("wb") as f:
        f.write(content[:100])
    assert expected_path.computehash("md5") != hash
    path, product_info = api.download(uuid, str(tmpdir), check_existing=True)
    assert expected_path.computehash("md5") == hash
    assert product_info == expected_product_info

    # Test MD5 check
    with expected_path.open("wb") as f:
        f.write(b'abcd' * 100)
    assert expected_path.computehash("md5") != hash
    with pytest.raises(InvalidChecksumError):
        api.download(uuid, str(tmpdir), check_existing=True, checksum=True)


@pytest.mark.scihub
def test_download_all(tmpdir):
    api = SentinelAPI(
        environ['SENTINEL_USER'],
        environ['SENTINEL_PASSWORD']
    )
    # From https://scihub.copernicus.eu/apihub/odata/v1/Products?$top=5&$orderby=ContentLength
    filenames = ["S1A_WV_OCN__2SSH_20150603T092625_20150603T093332_006207_008194_521E",
                 "S1A_WV_OCN__2SSV_20150526T211029_20150526T211737_006097_007E78_134A",
                 "S1A_WV_OCN__2SSV_20150526T081641_20150526T082418_006090_007E3E_104C"]

    api.query_raw(" OR ".join(filenames))
    assert len(api.get_products()) == len(filenames)

    # Download normally
    result = api.download_all(str(tmpdir))
    assert len(result) == len(filenames)
    for path, product_info in result.items():
        pypath = py.path.local(path)
        assert pypath.purebasename in filenames
        assert pypath.check(exists=1, file=1)
        assert pypath.size() == product_info["size"]

    # Force one download to fail
    path, product_info = list(result.items())[0]
    py.path.local(path).remove()
    with requests_mock.mock(real_http=True) as rqst:
        url = "https://scihub.copernicus.eu/apihub/odata/v1/Products('%s')/?$format=json" % product_info["id"]
        json = api.session.get(url).json()
        json["d"]["Checksum"]["Value"] = "00000000000000000000000000000000"
        rqst.get(url, json=json)
        result = api.download_all(str(tmpdir), max_attempts=1, checksum=True)
        assert len(result) == len(filenames)
        assert result[path] is None
