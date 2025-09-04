=================
Administrator Guide
=================

This guide is designed for system administrators, DevOps engineers, and technical users responsible for deploying, maintaining, and scaling PaperSorter installations.

Learn how to set up robust, production-ready deployments that can serve multiple users and handle large volumes of research papers efficiently.

Scope
=====

This guide covers:

- **Production deployment** strategies and best practices
- **Database administration** including setup, optimization, and maintenance
- **Security considerations** for multi-user environments
- **Monitoring and troubleshooting** common issues
- **Backup and disaster recovery** procedures

.. toctree::
   :maxdepth: 2

   authentication
   deployment
   database-setup
   backup-restore
   monitoring
   security
   troubleshooting

Key Responsibilities
====================

System Architecture
-------------------

- Database server management (PostgreSQL with pgvector)
- Web server configuration and load balancing
- Background task scheduling (cron jobs or task queues)
- API key and credential management

Operational Tasks
-----------------

- Regular database maintenance and optimization
- Model performance monitoring and retraining schedules
- User access management and authentication setup
- System resource monitoring and scaling decisions

Security Considerations
-----------------------

- OAuth provider configuration (Google, GitHub, ORCID)
- Database access controls and encryption
- API key rotation and secure storage
- Network security and SSL certificate management

Production Readiness
====================

Before deploying to production, ensure:

- Database backups are automated and tested
- Monitoring and alerting systems are in place
- Security policies are implemented and documented
- Disaster recovery procedures are established

Related Resources
=================

- :doc:`../development/index` - Contributing and extending PaperSorter
- :doc:`../api/index` - API reference for custom integrations