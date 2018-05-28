class Competition < ApplicationRecord

  validates :name, presence: true
  validates :date, presence: true
  validates :url, presence: true
  validates :competition_type, inclusion: { in: CompetitionType::TYPES }

  def description
    "#{date.year}: #{name}"
  end
end
