"""Initial schema migration

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-11-25 09:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # 1. Plants table
    op.create_table(
        'plants',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('species', sa.String(length=120), nullable=False, server_default='Unknown Plant'),
        sa.Column('category', sa.String(length=80), nullable=False, server_default='Houseplant'),
        sa.Column('image', sa.String(length=500), nullable=True),
        sa.Column('registered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('location', sa.String(length=120), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('health_status', sa.String(length=60), nullable=False, server_default='Unscanned'),
        sa.Column('pot_size_cm', sa.Integer(), nullable=False, server_default='15'),
        sa.Column('soil_type', sa.String(length=80), nullable=False, server_default='Potting Mix'),
        sa.Column('watering_frequency_days', sa.Integer(), nullable=False, server_default='7'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_plants_id', 'plants', ['id'], unique=False)
    op.create_index('ix_plants_name', 'plants', ['name'], unique=False)

    # 2. Devices table
    op.create_table(
        'devices',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('identifier', sa.String(length=80), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False, server_default='ESP32-CAM Sensor'),
        sa.Column('type', sa.String(length=60), nullable=False, server_default='ESP32-CAM'),
        sa.Column('status', sa.String(length=30), nullable=False, server_default='offline'),
        sa.Column('ip_address', sa.String(length=60), nullable=False, server_default=''),
        sa.Column('stream_url', sa.String(length=250), nullable=False, server_default=''),
        sa.Column('snapshot_url', sa.String(length=250), nullable=False, server_default=''),
        sa.Column('last_communication', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_image_received', sa.DateTime(timezone=True), nullable=True),
        sa.Column('poll_interval_sec', sa.Integer(), nullable=False, server_default='60'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_devices_id', 'devices', ['id'], unique=False)
    op.create_index('ix_devices_identifier', 'devices', ['identifier'], unique=True)

    # 3. Device Logs table
    op.create_table(
        'device_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('device_id', sa.Integer(), nullable=False),
        sa.Column('event_type', sa.String(length=40), nullable=False),
        sa.Column('message', sa.String(length=300), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['device_id'], ['devices.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_device_logs_id', 'device_logs', ['id'], unique=False)
    op.create_index('ix_device_logs_device_id', 'device_logs', ['device_id'], unique=False)

    # 4. Camera Images table
    op.create_table(
        'camera_images',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('device_id', sa.Integer(), nullable=True),
        sa.Column('plant_id', sa.Integer(), nullable=True),
        sa.Column('file_path', sa.String(length=500), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=True),
        sa.Column('file_size', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('width', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('height', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('processing_status', sa.String(length=40), nullable=False, server_default='received'),
        sa.Column('error_message', sa.String(length=300), nullable=False, server_default=''),
        sa.ForeignKeyConstraint(['device_id'], ['devices.id']),
        sa.ForeignKeyConstraint(['plant_id'], ['plants.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_camera_images_id', 'camera_images', ['id'], unique=False)
    op.create_index('ix_camera_images_device_id', 'camera_images', ['device_id'], unique=False)
    op.create_index('ix_camera_images_plant_id', 'camera_images', ['plant_id'], unique=False)

    # 5. Analyses table
    op.create_table(
        'analyses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('image_id', sa.Integer(), nullable=True),
        sa.Column('plant_id', sa.Integer(), nullable=False),
        sa.Column('device_id', sa.Integer(), nullable=True),
        sa.Column('image', sa.String(length=500), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=True),
        sa.Column('plant_identification', sa.String(length=120), nullable=True),
        sa.Column('plant_confidence', sa.Float(), nullable=True),
        sa.Column('disease_detected', sa.String(length=20), nullable=False, server_default='uncertain'),
        sa.Column('disease_name', sa.String(length=120), nullable=True),
        sa.Column('disease_confidence', sa.Float(), nullable=True),
        sa.Column('severity', sa.String(length=40), nullable=True),
        sa.Column('health_status', sa.String(length=60), nullable=False, server_default='Inconclusive'),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('symptoms', sa.Text(), nullable=True),
        sa.Column('recommendations', sa.Text(), nullable=True),
        sa.Column('prevention', sa.Text(), nullable=True),
        sa.Column('recovery_plan', sa.Text(), nullable=True),
        sa.Column('stress_status', sa.String(length=60), nullable=False, server_default='None'),
        sa.Column('stress_observations', sa.Text(), nullable=True),
        sa.Column('watering_status', sa.String(length=60), nullable=False, server_default='Watering condition uncertain'),
        sa.Column('watering_quantity_ml', sa.Integer(), nullable=True),
        sa.Column('watering_reason', sa.Text(), nullable=True),
        sa.Column('watering_instructions', sa.Text(), nullable=True),
        sa.Column('provider_engine', sa.String(length=80), nullable=False, server_default='FloraBOT Vision Engine'),
        sa.Column('provider_reference', sa.String(length=200), nullable=False, server_default=''),
        sa.Column('diagnostic_error', sa.Text(), nullable=False, server_default=''),
        sa.Column('detection_data_json', sa.Text(), nullable=False, server_default='[]'),
        sa.Column('detection_model_json', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('identification_candidates_json', sa.Text(), nullable=False, server_default='[]'),
        sa.Column('annotated_image_path', sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(['device_id'], ['devices.id']),
        sa.ForeignKeyConstraint(['image_id'], ['camera_images.id']),
        sa.ForeignKeyConstraint(['plant_id'], ['plants.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_analyses_id', 'analyses', ['id'], unique=False)
    op.create_index('ix_analyses_plant_id', 'analyses', ['plant_id'], unique=False)

    # 6. Reports table
    op.create_table(
        'reports',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('plant_id', sa.Integer(), nullable=False),
        sa.Column('analysis_id', sa.Integer(), nullable=True),
        sa.Column('pdf_path', sa.String(length=500), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('report_data_json', sa.Text(), nullable=False, server_default='{}'),
        sa.ForeignKeyConstraint(['analysis_id'], ['analyses.id']),
        sa.ForeignKeyConstraint(['plant_id'], ['plants.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_reports_id', 'reports', ['id'], unique=False)
    op.create_index('ix_reports_plant_id', 'reports', ['plant_id'], unique=False)

    # 7. Conversations table
    op.create_table(
        'conversations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('plant_id', sa.Integer(), nullable=True),
        sa.Column('title', sa.String(length=120), nullable=False, server_default='General Plant Consultation'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['plant_id'], ['plants.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_conversations_id', 'conversations', ['id'], unique=False)

    # 8. Messages table
    op.create_table(
        'messages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('conversation_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_messages_id', 'messages', ['id'], unique=False)
    op.create_index('ix_messages_conversation_id', 'messages', ['conversation_id'], unique=False)

    # 9. Knowledge Entries table
    op.create_table(
        'knowledge_entries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('topic', sa.String(length=120), nullable=False),
        sa.Column('species', sa.String(length=120), nullable=True),
        sa.Column('category', sa.String(length=60), nullable=False, server_default='general'),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('treatment', sa.Text(), nullable=True),
        sa.Column('prevention', sa.Text(), nullable=True),
        sa.Column('keywords', sa.String(length=250), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_knowledge_entries_id', 'knowledge_entries', ['id'], unique=False)
    op.create_index('ix_knowledge_entries_topic', 'knowledge_entries', ['topic'], unique=False)

def downgrade() -> None:
    op.drop_table('knowledge_entries')
    op.drop_table('messages')
    op.drop_table('conversations')
    op.drop_table('reports')
    op.drop_table('analyses')
    op.drop_table('camera_images')
    op.drop_table('device_logs')
    op.drop_table('devices')
    op.drop_table('plants')
