from base64 import b64decode

from ocp_resources.api_service import APIService
from ocp_resources.resource import NamespacedResource
from ocp_resources.secret import Secret

from utilities.virt import run_command


def is_certificates_validity_within_given_time(hco_namespace_name, seconds):
    """
    Verify if the CA and server certificates in CNV are valid within a given number of seconds using the openssl
    command with the -checkend argument.
    """
    openssl_checkend_cmd = "openssl x509 -checkend"
    tls_cert = get_base64_decoded_certificate(
        certificate_data=Secret(
            name="cdi-uploadproxy-server-cert", namespace=hco_namespace_name
        ).instance.data["tls.crt"]
    )
    api_service = get_base64_decoded_certificate(
        certificate_data=APIService(
            name=f"{NamespacedResource.ApiVersion.V1BETA1}.{NamespacedResource.ApiGroup.UPLOAD_CDI_KUBEVIRT_IO}"
        ).instance.spec.caBundle
    )
    certificates_results = {
        tls_cert: None,
        api_service: None,
    }
    for cert in certificates_results:
        _, out, err = run_command(
            command=[f"echo -e '{cert}' | {openssl_checkend_cmd} {seconds}"],
            shell=True,
        )
        certificates_results[cert] = (
            not err and out.strip() == "Certificate will not expire"
        )
    return certificates_results


def get_base64_decoded_certificate(certificate_data):
    return b64decode(certificate_data).decode(encoding="utf-8")
