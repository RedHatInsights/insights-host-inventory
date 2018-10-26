from app import db
from datetime import datetime
from sqlalchemy.dialects.postgresql import JSON, JSONB

class Host(db.Model):
    __tablename__ = 'hosts'

    id = db.Column(db.Integer, primary_key=True)
    account = db.Column(db.String(10))
    display_name = db.Column(db.String(200))
    created_on = db.Column(db.DateTime, 
                          default=datetime.utcnow)
    modified_on = db.Column(db.DateTime, 
                          default=datetime.utcnow,
                          onupdate=datetime.utcnow)
    facts = db.Column(JSONB)
    tags = db.Column(JSONB)
    canonical_facts = db.Column(JSONB)

    def __init__(self, canonical_facts, display_name=display_name, account=account, tags=None, facts=None):
        self.canonical_facts = canonical_facts
        self.display_name = display_name
        self.account = account
        self.tags = tags
        self.facts = facts

    @classmethod
    def from_json(cls, d):
          return cls(
              d.get("canonical_facts"),
              d.get("display_name"),
              d.get("account"),
              d.get("tags"),
              d.get("facts")
          )

    def to_json(self):
        return {
                 "canonical_facts": self.canonical_facts,
                 "id": self.id,
                 "account": self.account,
                 "display_name": self.display_name,
                 "tags": self.tags,
                 "facts": self.facts
               }


    def save(self):
        db.session.add(self)
        db.session.commit()

    @staticmethod
    def get_all():
        return Host.query.all()

    def delete(self):
        db.session.delete(self)
        db.session.commit()

    def __repr__(self):
        tmpl = "<Host '%s' '%d' canonical_facts=%s facts=%s tags=%s>"
        return tmpl % (self.display_name, self.id, self.canonical_facts, self.facts, self.tags)
