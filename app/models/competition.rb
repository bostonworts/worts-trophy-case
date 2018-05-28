class Competition < ApplicationRecord
  TYPES = %w(
    bjcp_sanctioned
    mcab_qualifier
    mcab_finals
    nhc_qualifier
    nhc_finals
  ).freeze.map(&:freeze)

  validates :name, presence: true
  validates :date, presence: true
  validates :url, presence: true
  validates :competition_type, inclusion: { in: TYPES }

  def description
    "#{date.year}: #{name}"
  end
end
