class User < ApplicationRecord
  DEFAULT_NAME = "Worts Member".freeze

  validates :email, presence: true, uniqueness: { case_sensitive: false }
  validates :full_name, presence: true, uniqueness: { unless: :has_default_name? }

  passwordless_with :email

  def can_delete?(trophy)
    owns_trophy?(trophy)
  end

  def can_edit?(trophy)
    owns_trophy?(trophy)
  end

  def deactivated?
    deactivated_at.present?
  end

  def has_default_name?
    full_name == DEFAULT_NAME
  end

  private

  def owns_trophy?(trophy)
    trophy.user == self
  end
end
