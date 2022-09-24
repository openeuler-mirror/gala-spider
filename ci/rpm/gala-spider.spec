%define debug_package %{nil}

Name:		gala-spider
Version:	1.0.0
Release:	1
Summary:	OS topological graph storage service and cause inference service for gala-ops project
License:	MulanPSL2
URL:		https://gitee.com/openeuler/gala-spider
Source0:	%{name}-%{version}.tar.gz

BuildRequires:  python3-setuptools systemd
Requires:   python3-%{name} = %{version}-%{release}


%description
OS topological graph storage service for gala-ops project


%package -n python3-%{name}
Summary:    Python3 package of gala-spider
Requires:   python3-kafka-python python3-pyyaml python3-pyarango python3-requests

%description -n python3-%{name}
Python3 package of gala-spider


%package -n gala-inference
Summary:    Cause inference module for gala-ops project
Requires:   python3-gala-inference = %{version}-%{release}

%description -n gala-inference
Cause inference module for A-Ops project


%package -n python3-gala-inference
Summary:    Python3 package of gala-inference
Requires:   python3-%{name} = %{version}-%{release} python3-networkx python3-scipy

%description -n python3-gala-inference
Python3 package of gala-inference


%prep
%autosetup


%build
%py3_build


%install
%py3_install


%pre
if [ -f "%{_unitdir}/gala-spider.service" ] ; then
        systemctl enable gala-spider.service || :
fi

%post
%systemd_post gala-spider.service

%preun
%systemd_preun gala-spider.service

%postun
%systemd_postun gala-spider.service


%pre -n gala-inference
if [ -f "%{_unitdir}/gala-inference.service" ] ; then
        systemctl enable gala-inference.service || :
fi

%post -n gala-inference
%systemd_post gala-inference.service

%preun -n gala-inference
%systemd_preun gala-inference.service

%postun -n gala-inference
%systemd_postun gala-inference.service


%files
%doc README.md docs/*
%license LICENSE
%config(noreplace) %{_sysconfdir}/%{name}/gala-spider.yaml
%config(noreplace) %{_sysconfdir}/%{name}/topo-relation.yaml
%config(noreplace) %{_sysconfdir}/%{name}/ext-observe-meta.yaml
%{_bindir}/spider-storage
%{_unitdir}/gala-spider.service


%files -n python3-%{name}
%{python3_sitelib}/spider/*
%{python3_sitelib}/gala_spider-*.egg-info


%files -n gala-inference
%doc README.md docs/*
%license LICENSE
%config(noreplace) %{_sysconfdir}/gala-inference/gala-inference.yaml
%config(noreplace) %{_sysconfdir}/gala-inference/ext-observe-meta.yaml
%config(noreplace) %{_sysconfdir}/gala-inference/infer-rule.yaml
%{_bindir}/gala-inference
%{_unitdir}/gala-inference.service


%files -n python3-gala-inference
%{python3_sitelib}/cause_inference/*
%{python3_sitelib}/gala_spider-*.egg-info


%changelog
* Fri Sep 23 2022 algorithmofdish<hexiujun1@huawei.com> - 1.0.0-1
- Package init
