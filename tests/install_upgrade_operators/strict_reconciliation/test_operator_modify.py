import pytest

from tests.install_upgrade_operators.strict_reconciliation.utils import verify_specs


class TestOperatorsModify:
    @pytest.mark.parametrize(
        "updated_cdi_cr",
        [
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "certConfig": {
                                "ca": {
                                    "duration": "9h",
                                    "renewBefore": "2h",
                                },
                                "server": {
                                    "duration": "3h",
                                    "renewBefore": "1h",
                                },
                            }
                        }
                    }
                },
                marks=pytest.mark.polarion("CNV-6312"),
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "certConfig": {
                                "ca": {
                                    "duration": "99h",
                                }
                            }
                        }
                    }
                },
                marks=pytest.mark.polarion("CNV-6315"),
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "certConfig": {
                                "ca": {
                                    "renewBefore": "2h",
                                },
                            }
                        }
                    }
                },
                marks=pytest.mark.polarion("CNV-6318"),
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "certConfig": {
                                "server": {
                                    "duration": "33h",
                                },
                            }
                        }
                    }
                },
                marks=pytest.mark.polarion("CNV-6321"),
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "certConfig": {
                                "server": {
                                    "renewBefore": "1h",
                                },
                            }
                        }
                    }
                },
                marks=pytest.mark.polarion("CNV-6324"),
            ),
        ],
        indirect=True,
    )
    def test_modify_cdi_cr(
        self,
        admin_client,
        hco_namespace,
        hco_spec,
        kubevirt_hyperconverged_spec_scope_function,
        cdi_spec,
        cnao_spec,
        updated_cdi_cr,
    ):
        assert verify_specs(
            admin_client,
            hco_namespace,
            hco_spec,
            kubevirt_hyperconverged_spec_scope_function,
            cdi_spec,
            cnao_spec,
        )

    @pytest.mark.parametrize(
        "updated_kubevirt_cr",
        [
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "certificateRotateStrategy": {
                                "selfSigned": {
                                    "ca": {
                                        "duration": "9h",
                                        "renewBefore": "2h",
                                    },
                                    "server": {
                                        "duration": "3h",
                                        "renewBefore": "1h",
                                    },
                                }
                            }
                        }
                    }
                },
                marks=pytest.mark.polarion("CNV-6313"),
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "certificateRotateStrategy": {
                                "selfSigned": {
                                    "ca": {
                                        "duration": "99h",
                                    }
                                }
                            }
                        }
                    }
                },
                marks=pytest.mark.polarion("CNV-6316"),
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "certificateRotateStrategy": {
                                "selfSigned": {
                                    "ca": {
                                        "renewBefore": "2h",
                                    },
                                }
                            }
                        }
                    }
                },
                marks=pytest.mark.polarion("CNV-6319"),
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "certificateRotateStrategy": {
                                "selfSigned": {
                                    "server": {
                                        "duration": "33h",
                                    },
                                }
                            }
                        }
                    }
                },
                marks=pytest.mark.polarion("CNV-6322"),
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "certificateRotateStrategy": {
                                "selfSigned": {
                                    "server": {
                                        "renewBefore": "1h",
                                    },
                                }
                            }
                        }
                    }
                },
                marks=pytest.mark.polarion("CNV-6325"),
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "configuration": {
                                "migrations": {
                                    "bandwidthPerMigration": "32Ki",
                                    "completionTimeoutPerGiB": 777,
                                    "parallelMigrationsPerCluster": 3,
                                    "parallelOutboundMigrationsPerNode": 4,
                                    "progressTimeout": 1500,
                                }
                            }
                        }
                    }
                },
                marks=pytest.mark.polarion("CNV-6328"),
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "configuration": {
                                "migrations": {"bandwidthPerMigration": "32Ki"}
                            }
                        }
                    }
                },
                marks=pytest.mark.polarion("CNV-6331"),
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "configuration": {
                                "migrations": {
                                    "completionTimeoutPerGiB": 777,
                                }
                            }
                        }
                    }
                },
                marks=pytest.mark.polarion("CNV-6334"),
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "configuration": {
                                "migrations": {
                                    "parallelMigrationsPerCluster": 3,
                                }
                            }
                        }
                    }
                },
                marks=pytest.mark.polarion("CNV-6337"),
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "configuration": {
                                "migrations": {
                                    "parallelOutboundMigrationsPerNode": 4,
                                }
                            }
                        }
                    }
                },
                marks=pytest.mark.polarion("CNV-6340"),
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "configuration": {"migrations": {"progressTimeout": 1500}}
                        }
                    }
                },
                marks=pytest.mark.polarion("CNV-6343"),
            ),
        ],
        indirect=True,
    )
    def test_modify_kubevirt_cr(
        self,
        admin_client,
        hco_namespace,
        hco_spec,
        kubevirt_hyperconverged_spec_scope_function,
        cdi_spec,
        cnao_spec,
        updated_kubevirt_cr,
    ):
        assert verify_specs(
            admin_client,
            hco_namespace,
            hco_spec,
            kubevirt_hyperconverged_spec_scope_function,
            cdi_spec,
            cnao_spec,
        )

    @pytest.mark.parametrize(
        "updated_cnao_cr",
        [
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "selfSignConfiguration": {
                                "caOverlapInterval": "2h",
                                "caRotateInterval": "9h",
                                "certOverlapInterval": "2h",
                                "certRotateInterval": "3h",
                            }
                        }
                    }
                },
                marks=pytest.mark.polarion("CNV-6314"),
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "selfSignConfiguration": {
                                "caRotateInterval": "99h",
                            }
                        }
                    }
                },
                marks=pytest.mark.polarion("CNV-6317"),
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "selfSignConfiguration": {
                                "caOverlapInterval": "2h",
                            }
                        }
                    }
                },
                marks=pytest.mark.polarion("CNV-6320"),
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "selfSignConfiguration": {
                                "certRotateInterval": "33h",
                            }
                        }
                    }
                },
                marks=pytest.mark.polarion("CNV-6323"),
            ),
            pytest.param(
                {
                    "patch": {
                        "spec": {
                            "selfSignConfiguration": {
                                "certOverlapInterval": "1h",
                            }
                        }
                    }
                },
                marks=pytest.mark.polarion("CNV-6326"),
            ),
        ],
        indirect=True,
    )
    def test_modify_cnao_cr(
        self,
        admin_client,
        hco_namespace,
        hco_spec,
        kubevirt_hyperconverged_spec_scope_function,
        cdi_spec,
        cnao_spec,
        updated_cnao_cr,
    ):
        assert verify_specs(
            admin_client,
            hco_namespace,
            hco_spec,
            kubevirt_hyperconverged_spec_scope_function,
            cdi_spec,
            cnao_spec,
        )
